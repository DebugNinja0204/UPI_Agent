"""
Agent Scheduler

Optional APScheduler integration for auto-running agent cycles.
Only used in development mode.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = None


def init_scheduler(app):
    """
    Initialize and start the scheduler.
    
    Only runs in development mode.
    Runs agent cycle every 2 minutes by default.
    
    Args:
        app: Flask application instance
    """
    global _scheduler
    
    # Only enable in development mode
    if app.config.get('ENV') != 'development':
        logger.info("Scheduler disabled (not in development mode)")
        return
    
    # Check if APScheduler is installed
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning(
            "APScheduler not installed. "
            "Install with: pip install apscheduler"
        )
        return
    
    try:
        from app.agent import run_agent_cycle
        
        # Create scheduler
        _scheduler = BackgroundScheduler()
        
        def scheduled_cycle():
            """Run agent cycle with app context."""
            with app.app_context():
                try:
                    results = run_agent_cycle()
                    logger.info(
                        f"Scheduled agent cycle completed: "
                        f"processed={results['disputes_processed']}"
                    )
                except Exception as e:
                    logger.error(f"Scheduled agent cycle failed: {str(e)}")
        
        # Add job to run every 2 minutes
        _scheduler.add_job(
            scheduled_cycle,
            trigger=IntervalTrigger(seconds=120),
            id='agent_cycle_job',
            name='Dispute Agent Cycle',
            replace_existing=True,
            coalesce=True,  # Don't run multiple times if delayed
            max_instances=1,  # Only one instance at a time
        )
        
        # Start scheduler
        _scheduler.start()
        logger.info("Agent scheduler started (interval: 120 seconds)")
    
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {str(e)}")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    
    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown()
            logger.info("Agent scheduler shutdown")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {str(e)}")
