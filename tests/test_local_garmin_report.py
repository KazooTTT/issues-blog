import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('local_report', Path(__file__).parents[1] / 'scripts/local-garmin-report.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class LocalReportTests(unittest.TestCase):
    def test_delivery_reuses_snapshot_and_never_calls_github(self):
        with tempfile.TemporaryDirectory() as directory:
            args = Namespace(date=date(2026, 10, 19), state_dir=Path(directory), input=None, send=True)
            with patch.dict(m.os.environ, {'TELEGRAM_CHAT_ID': '123', 'TELEGRAM_BOT_TOKEN': 'secret'}), \
                 patch.object(m, 'fetch_payload', return_value={}), \
                 patch.object(m.reports, 'sleep_report', return_value=('早报', '指标')), \
                 patch.object(m, 'interpret', return_value='解读') as model, \
                 patch.object(m.reports, 'api', return_value={'ok': True}) as api:
                m.run(args)
                m.run(args)
                self.assertEqual(model.call_count, 1)
                self.assertEqual(api.call_count, 1)
                self.assertTrue(api.call_args.args[0].startswith('https://api.telegram.org/'))
                self.assertEqual(api.call_args.kwargs['data']['parse_mode'], 'HTML')
                self.assertIn('<b>早报</b>', api.call_args.kwargs['data']['text'])
                self.assertNotIn('原始指标', api.call_args.kwargs['data']['text'])

    def test_uncertain_send_is_not_automatically_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            args = Namespace(date=date(2026, 10, 19), state_dir=Path(directory), input=None, send=True)
            with patch.dict(m.os.environ, {'TELEGRAM_CHAT_ID': '123', 'TELEGRAM_BOT_TOKEN': 'secret'}), \
                 patch.object(m, 'fetch_payload', return_value={}), \
                 patch.object(m.reports, 'sleep_report', return_value=('早报', '指标')), \
                 patch.object(m, 'interpret', return_value='解读'), \
                 patch.object(m.reports, 'api', side_effect=m.reports.ReportError('timeout')) as api:
                with self.assertRaises(m.reports.ReportError):
                    m.run(args)
                with self.assertRaisesRegex(m.reports.ReportError, 'uncertain'):
                    m.run(args)
                self.assertEqual(api.call_count, 1)

    def test_model_failure_keeps_source_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            args = Namespace(date=date(2026, 10, 19), state_dir=Path(directory), input=None, send=False)
            with patch.object(m, 'fetch_payload', return_value={}) as fetch, \
                 patch.object(m.reports, 'sleep_report', return_value=('早报', '指标')), \
                 patch.object(m, 'interpret', side_effect=[m.reports.ReportError('offline'), '解读']):
                with self.assertRaises(m.reports.ReportError):
                    m.run(args)
                m.run(args)
                self.assertEqual(fetch.call_count, 1)
                self.assertTrue(json.loads((Path(directory) / '2026-10-19.json').read_text())['source'].startswith('指标'))

    def test_gateway_must_be_local(self):
        with patch.dict(m.os.environ, {'MAGPIE_BASE_URL': 'https://example.com/v1'}):
            with self.assertRaises(m.reports.ReportError):
                m.interpret('早报', '指标')

    def test_truncated_model_response_is_rejected(self):
        with patch.dict(m.os.environ, {'MAGPIE_API_KEY': 'local', 'MAGPIE_BASE_URL': 'http://127.0.0.1:3425/v1'}), \
             patch.object(m.reports, 'api', return_value={'choices': [{'message': {'content': '半句话'}, 'finish_reason': 'length'}]}):
            with self.assertRaises(m.reports.ReportError):
                m.interpret('早报', '指标')

    def test_telegram_html_formats_markdown_and_escapes_raw_html(self):
        text = '# 早报\n\n**重点** 与 *建议*\n- HRV < 50 & 未知\n`**原样**`\n<script>x</script>'
        result = m.telegram_html(text)
        self.assertIn('<b>早报</b>', result)
        self.assertIn('<b>重点</b> 与 <i>建议</i>', result)
        self.assertIn('• HRV &lt; 50 &amp; 未知', result)
        self.assertIn('<code>**原样**</code>', result)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', result)

    def test_telegram_html_handles_links_code_and_escaped_markdown(self):
        result = m.telegram_html('[来源](https://example.com/?a=1&b=2)\n```\n<x> **raw**\n```\n\\*literal\\*')
        self.assertIn('<a href="https://example.com/?a=1&amp;b=2">来源</a>', result)
        self.assertIn('<pre>&lt;x&gt; **raw**</pre>', result)
        self.assertTrue(result.endswith('*literal*'))

    def test_recovery_source_hrv_baseline_and_beijing_yesterday(self):
        payload = {'localContext': {
            'hrv': {'hrvSummary': {'calendarDate': '2026-10-19', 'lastNightAvg': 35, 'weeklyAvg': 45,
                                     'status': 'BALANCED', 'baseline': {'balancedLow': 40, 'balancedUpper': 55}}},
            'activities': [
                {'activityId': 1, 'startTimeGMT': '2026-10-17 16:30:00', 'duration': 3600,
                 'activityType': {'typeKey': 'running'}, 'averageHR': 140, 'activityTrainingLoad': 50},
                {'activityId': 1, 'startTimeGMT': '2026-10-17 16:30:00', 'duration': 3600},
                {'activityId': 2, 'startTimeGMT': '2026-10-18 16:30:00', 'duration': 999},
            ]}}
        text = m.recovery_source('2026-10-19', payload)
        self.assertIn('40–55 ms', text)
        self.assertIn('昨夜值相对个人基线：低于', text)
        self.assertIn('7日均值相对个人基线：处于', text)
        self.assertIn('共 1 次', text)
        self.assertIn('1 小时 0 分钟', text)
        self.assertIn('140 bpm', text)
        self.assertIn('训练负荷：50', text)

    def test_missing_context_and_failed_query_are_not_zero_activity(self):
        # 没有记录时整段不出现，不写“未找到运动”这类填充。
        self.assertNotIn('昨日运动', m.recovery_source('2026-10-19', {}))
        text = m.recovery_source('2026-10-19', {'localContext': {'hrv_error': True, 'activities_error': True}})
        self.assertIn('运动接口读取失败', text)
        self.assertIn('HRV 接口读取失败', text)
        self.assertNotIn('共 0 次', text)

    def test_empty_activity_list_has_no_exercise_section(self):
        text = m.recovery_source('2026-10-19', {'localContext': {'activities': []}})
        self.assertNotIn('## 昨日运动', text)
        other_day = {'localContext': {'activities': [
            {'activityId': 3, 'startTimeGMT': '2026-10-15 02:00:00', 'duration': 600}]}}
        self.assertNotIn('## 昨日运动', m.recovery_source('2026-10-19', other_day))

    def test_stale_hrv_date_does_not_supply_baseline(self):
        text = m.recovery_source('2026-10-19', {'localContext': {'hrv': {'hrvSummary': {
            'calendarDate': '2026-10-18', 'baseline': {'balancedLow': 40, 'balancedUpper': 55}}}}})
        self.assertNotIn('40–55', text)
        self.assertIn('不能推算', text)

    def test_chunks_have_balanced_html_and_safe_utf16_lengths(self):
        from html.parser import HTMLParser
        class Validator(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.text = ''
            def handle_starttag(self, tag, attrs):
                self.stack.append(tag)
            def handle_endtag(self, tag):
                self.asserted = self.stack.pop()
                if self.asserted != tag:
                    raise AssertionError('Unbalanced formatting')
            def handle_data(self, text):
                self.text += text
        source = '## 恢复建议\n\n**' + ('睡眠😀 < & 很重要。\n\n' * 400) + '**\n```\n' + 'x' * 7000 + '\n```'
        chunks = m.telegram_chunks(m.telegram_html(source))
        self.assertGreater(len(chunks), 2)
        for i, chunk in enumerate(chunks, 1):
            parser = Validator()
            parser.feed(chunk)
            self.assertEqual(parser.stack, [])
            self.assertLessEqual(len(parser.text.encode('utf-16-le')) // 2, 4096)
            self.assertIn(f'{i}/{len(chunks)}', chunk)

    def test_partial_delivery_does_not_repeat_confirmed_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            args = Namespace(date=date(2026, 10, 19), state_dir=Path(directory), input=None, send=True)
            failure = {'ok': False}
            with patch.dict(m.os.environ, {'TELEGRAM_CHAT_ID': '123', 'TELEGRAM_BOT_TOKEN': 'secret'}), \
                 patch.object(m, 'fetch_payload', return_value={}), \
                 patch.object(m.reports, 'sleep_report', return_value=('早报', '指标')), \
                 patch.object(m, 'interpret', return_value='解读'), \
                 patch.object(m, 'report_chunks', return_value=['第一条', '第二条']), \
                 patch.object(m.reports, 'api', side_effect=[{'ok': True, 'result': {'message_id': 1}}, failure,
                                                           {'ok': True, 'result': {'message_id': 2}}]) as api:
                with self.assertRaises(m.reports.ReportError):
                    m.run(args)
                m.run(args)
                self.assertEqual([call.kwargs['data']['text'] for call in api.call_args_list], ['第一条', '第二条', '第二条'])


    def test_brief_structure_and_action_limit(self):
        data = {"conclusion": "今天优先恢复。", "sleep": "睡眠7小时，评分75。", "hrv": "昨夜42 ms，基线43–72 ms。",
                "exercise": "昨日舞蹈57分钟，负荷293。", "fitness": "长期底子还在，最近一周压得比较重。",
                "actions": ["今天安排轻松活动。", "今晚提早入睡。"]}
        result = m.render_brief(json.dumps(data))
        self.assertEqual(result.count("## "), 4)
        without = m.render_brief(json.dumps(data), False)
        self.assertNotIn("昨日运动", without)
        self.assertEqual(without.count("## "), 3)
        self.assertEqual(result.count("42 ms"), 1)
        self.assertTrue(result.startswith("今天优先恢复。"))
        data['actions'] = ['建议'] * 4
        with self.assertRaises(m.reports.ReportError):
            m.render_brief(json.dumps(data))

    def test_notification_excludes_local_source(self):
        chunks = m.report_chunks({'title': '早报', 'interpretation': '精简解读', 'source': '原始指标仅本地保留'})
        self.assertEqual(len(chunks), 1)
        self.assertNotIn('原始指标', chunks[0])
