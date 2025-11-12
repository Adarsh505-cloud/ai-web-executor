from __future__ import annotations

import argparse
import sys
import logging
from pathlib import Path

from .planner import plan_with_bedrock
from .executor import run_plan

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description="AI Web Executor (Planner + Executor)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic timesheet automation
  python -m app.main "Login and add daily timesheet" --slowmo 250
  
  # With specific URL
  python -m app.main "Navigate to URL, login, add timesheet" --slowmo 250
        """
    )
    parser.add_argument(
        "prompt",
        help="Natural language instruction for web automation"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (no visible browser)"
    )
    parser.add_argument(
        "--slowmo",
        type=int,
        default=150,
        help="Slow motion in milliseconds for debugging (default: 150)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30000,
        help="Default timeout in milliseconds (default: 30000)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create artifacts directory
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    (artifacts_dir / "videos").mkdir(exist_ok=True)
    (artifacts_dir / "traces").mkdir(exist_ok=True)
    
    try:
        logger.info("=" * 70)
        logger.info("AI WEB EXECUTOR - Starting")
        logger.info("=" * 70)
        
        # Generate plan
        logger.info("Generating execution plan from prompt...")
        plan = plan_with_bedrock(args.prompt)
        
        logger.info("=" * 70)
        logger.info("EXECUTION PLAN")
        logger.info("=" * 70)
        for i, action in enumerate(plan.actions, 1):
            selector_display = (action.selector or 'N/A')[:40]
            value_display = (str(action.value) or 'N/A')[:40]
            logger.info(f"{i:2d}. {action.type:20s} | selector={selector_display:40s} | value={value_display}")
        logger.info("=" * 70)
        
        # Execute plan
        logger.info("Executing plan...")
        run_plan(plan, headed=not args.headless, slow_mo_ms=args.slowmo)
        
        logger.info("=" * 70)
        logger.info("✓ EXECUTION COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        sys.exit(0)
    
    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user")
        sys.exit(130)
    
    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"✗ EXECUTION FAILED: {type(e).__name__}")
        logger.error(f"Error: {e}")
        logger.error("=" * 70)
        logger.info("Check artifacts/ directory for screenshots and traces")
        sys.exit(1)

if __name__ == "__main__":
    main()
