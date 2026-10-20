declare module "cloudflare:workers" {
  import type { D1Binding } from "@/data/workout-store";

  export const env: {
    DB?: D1Binding;
  };
}
