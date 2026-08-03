import type { SourceIssue, WorkoutReview } from "./types";

export const WORKOUT_REVIEW_LABEL = "workout:review";

const WORKOUT_REVIEW_MARKER = /<!--\s*workout-review:v1\s*-->/i;
const WORKOUT_ID_MARKER = /<!--\s*workout-id:\s*([^\s]+)\s*-->/i;

function toWorkoutReview(issue: SourceIssue): WorkoutReview {
  if (!WORKOUT_REVIEW_MARKER.test(issue.body)) {
    throw new Error(
      `Workout review Issue #${issue.number} is missing <!-- workout-review:v1 -->`,
    );
  }

  const workoutId = issue.body.match(WORKOUT_ID_MARKER)?.[1];
  if (!workoutId) {
    throw new Error(
      `Workout review Issue #${issue.number} is missing <!-- workout-id: ... -->`,
    );
  }

  return { ...issue, workoutId };
}

export function classifyWorkoutReviews(
  ownedIssues: SourceIssue[],
): WorkoutReview[] {
  const reviews = ownedIssues
    .filter((issue) => issue.labels.includes(WORKOUT_REVIEW_LABEL))
    .map(toWorkoutReview);

  const issueByWorkoutId = new Map<string, number>();
  for (const review of reviews) {
    const existingIssue = issueByWorkoutId.get(review.workoutId);
    if (existingIssue !== undefined) {
      throw new Error(
        `Workout ${review.workoutId} has multiple reviews: Issues #${existingIssue} and #${review.number}`,
      );
    }
    issueByWorkoutId.set(review.workoutId, review.number);
  }

  return reviews;
}

export function indexWorkoutReviews(
  reviews: WorkoutReview[],
  workoutIds: Iterable<string>,
): Map<string, WorkoutReview> {
  const knownWorkoutIds = new Set(workoutIds);
  const reviewsByWorkoutId = new Map<string, WorkoutReview>();

  for (const review of reviews) {
    if (!knownWorkoutIds.has(review.workoutId)) {
      throw new Error(
        `Workout review Issue #${review.number} references unknown workout ${review.workoutId}`,
      );
    }
    reviewsByWorkoutId.set(review.workoutId, review);
  }

  return reviewsByWorkoutId;
}
