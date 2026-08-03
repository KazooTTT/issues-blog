export interface LabelEvent {
  label: string;
  createdAt: string;
}

export interface ReactionSummary {
  content: string;
  count: number;
}

export interface SourceComment {
  id: string;
  body: string;
  url: string;
  author: string;
  avatarUrl: string;
  createdAt: string;
  updatedAt: string;
  reactions: ReactionSummary[];
}

export interface SourceIssue {
  number: number;
  title: string;
  body: string;
  url: string;
  author: string;
  state: "OPEN" | "CLOSED";
  createdAt: string;
  updatedAt: string;
  labels: string[];
  labelEvents: LabelEvent[];
  reactions: ReactionSummary[];
  comments: SourceComment[];
}

export interface Post extends SourceIssue {
  publishedAt: string;
  tags: string[];
  featured: boolean;
  permalink: string;
}

export interface WorkoutReview extends SourceIssue {
  workoutId: string;
}

export interface SiteContent {
  posts: Post[];
  workoutReviews: WorkoutReview[];
  about?: SourceIssue;
  warnings: string[];
}
