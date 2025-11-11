import argparse
import os
from .planner import plan_with_bedrock
from .executor import run_plan

def main():
    parser = argparse.ArgumentParser(description="AI Web Executor (Planner + Executor)")
    parser.add_argument("prompt", help="Natural language instruction (e.g., 'Open http://localhost:8000/login.html ...')")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--slowmo", type=int, default=150, help="Slow motion in ms for debugging")
    args = parser.parse_args()

    os.makedirs("artifacts/videos", exist_ok=True)

    plan = plan_with_bedrock(args.prompt)
    print("=== PLAN ===")
    for i, a in enumerate(plan.actions, 1):
        print(i, a.model_dump())

    run_plan(plan, headed=not args.headless, slow_mo_ms=args.slowmo)

if __name__ == "__main__":
    main()
