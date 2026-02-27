"""
Dispute Resolution Agent CLI

Runs the background agent for automated dispute processing.

Usage:
    python run_agent.py run              # Run one cycle
    python run_agent.py schedule         # Run with APScheduler (every 2 min)
    python run_agent.py daemon           # Run continuously (1 sec delay between cycles)
"""

import click
import logging
import signal
import sys
from datetime import datetime
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Dispute Resolution Agent CLI"""
    pass


@cli.command()
def run():
    """Run one agent cycle immediately."""
    logger.info("Starting agent cycle...")
    
    try:
        from app import create_app
        from app.agent import run_agent_cycle
        
        # Create app context
        app = create_app('development')
        
        with app.app_context():
            results = run_agent_cycle()
            
            # Print summary
            click.echo("\n" + "=" * 60)
            click.echo("CYCLE RESULTS")
            click.echo("=" * 60)
            click.echo(f"Processed: {results['disputes_processed']}")
            click.echo(f"Verified: {results['disputes_verified']}")
            click.echo(f"Refunded: {results['disputes_refunded']}")
            click.echo(f"Failed: {results['disputes_failed']}")
            
            if results['errors']:
                click.echo(f"\nErrors: {len(results['errors'])}")
                for error in results['errors'][:3]:
                    click.echo(f"  - {error['type']}: {error['message']}")
            
            click.echo("=" * 60 + "\n")
            
            return 0
    
    except Exception as e:
        logger.error(f"Agent cycle failed: {str(e)}")
        click.echo(f"Error: {str(e)}", err=True)
        return 1


@cli.command()
@click.option(
    '--interval',
    default=120,
    type=int,
    help='Interval between cycles in seconds (default: 120)'
)
def schedule(interval):
    """Run agent with APScheduler (auto-schedule every N seconds)."""
    logger.info(f"Starting agent scheduler (interval: {interval}s)...")
    
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        import atexit
        
        from app import create_app
        from app.agent import run_agent_cycle
        
        # Create app
        app = create_app('development')
        
        # Setup scheduler
        scheduler = BackgroundScheduler()
        
        def scheduled_cycle():
            """Scheduled agent cycle execution."""
            with app.app_context():
                try:
                    results = run_agent_cycle()
                    logger.info(
                        f"Cycle completed: "
                        f"processed={results['disputes_processed']}, "
                        f"verified={results['disputes_verified']}, "
                        f"refunded={results['disputes_refunded']}, "
                        f"failed={results['disputes_failed']}"
                    )
                except Exception as e:
                    logger.error(f"Scheduled cycle failed: {str(e)}")
        
        # Add job
        scheduler.add_job(
            scheduled_cycle,
            trigger=IntervalTrigger(seconds=interval),
            id='dispute_agent_cycle',
            name='Dispute Resolution Agent Cycle',
            replace_existing=True,
        )
        
        # Cleanup on exit
        atexit.register(lambda: scheduler.shutdown())
        
        # Start scheduler
        scheduler.start()
        click.echo(f"Agent scheduler started (interval: {interval}s)")
        click.echo("Press Ctrl+C to stop")
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Agent scheduler stopped by user")
            return 0
    
    except ImportError:
        click.echo(
            "APScheduler not installed. Install with: pip install apscheduler",
            err=True
        )
        return 1
    
    except Exception as e:
        logger.error(f"Scheduler failed: {str(e)}")
        click.echo(f"Error: {str(e)}", err=True)
        return 1


@cli.command()
@click.option(
    '--delay',
    default=1,
    type=int,
    help='Delay between cycles in seconds (default: 1)'
)
def daemon(delay):
    """Run agent continuously (simple daemon loop)."""
    logger.info(f"Starting agent daemon (delay: {delay}s)...")
    
    try:
        from app import create_app
        from app.agent import run_agent_cycle
        
        # Create app
        app = create_app('development')
        
        cycle_count = 0
        
        def signal_handler(sig, frame):
            """Handle Ctrl+C gracefully."""
            logger.info(f"Agent daemon stopped by user (ran {cycle_count} cycles)")
            sys.exit(0)
        
        # Register signal handler
        signal.signal(signal.SIGINT, signal_handler)
        
        click.echo("Agent daemon started")
        click.echo("Press Ctrl+C to stop")
        
        # Main loop
        while True:
            with app.app_context():
                try:
                    cycle_count += 1
                    results = run_agent_cycle()
                    
                    logger.info(
                        f"Cycle #{cycle_count}: "
                        f"processed={results['disputes_processed']}, "
                        f"verified={results['disputes_verified']}, "
                        f"refunded={results['disputes_refunded']}"
                    )
                
                except Exception as e:
                    logger.error(f"Cycle #{cycle_count} failed: {str(e)}")
                
                # Wait before next cycle
                time.sleep(delay)
    
    except Exception as e:
        logger.error(f"Daemon failed: {str(e)}")
        click.echo(f"Error: {str(e)}", err=True)
        return 1


if __name__ == '__main__':
    cli()
