import asyncio
import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from .logging import WorkflowLogger

class WorkflowExecutor:
    def __init__(
        self,
        max_workers: int = 3,
        timeout: int = 3600,
        continuous_load: bool = False,
        load_churn_interval: int = 300
    ):
        self.max_workers = max_workers
        self.timeout = timeout
        self.continuous_load = continuous_load
        self.load_churn_interval = load_churn_interval
        self.workflow_statuses: Dict[str, Dict[str, Any]] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.logger = logging.getLogger(__name__)
        self._stop_event = asyncio.Event()

    async def execute_workflows(
        self,
        workflows: Dict[str, Dict[str, Any]],
        load_workflow: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute multiple workflows in parallel with continuous load if specified."""
        try:
            # Start continuous load if specified
            if self.continuous_load and load_workflow:
                asyncio.create_task(self._run_continuous_load(load_workflow))

            # Execute chaos scenarios in parallel
            tasks = []
            for name, workflow in workflows.items():
                if workflow.get('enabled', False):
                    task = asyncio.create_task(
                        self._execute_single_workflow(name, workflow)
                    )
                    tasks.append(task)

            # Wait for all chaos scenarios to complete
            await asyncio.gather(*tasks)

        except Exception as e:
            self.logger.error(f"Error executing workflows: {str(e)}")
            raise

    async def _run_continuous_load(self, load_workflow: Dict[str, Any]) -> None:
        """Run continuous load with churn."""
        while not self._stop_event.is_set():
            try:
                # Execute load generation
                await self._execute_single_workflow('continuous_load', load_workflow)
                
                # Wait for churn interval
                await asyncio.sleep(self.load_churn_interval)
                
            except Exception as e:
                self.logger.error(f"Error in continuous load: {str(e)}")
                # Don't break the loop on error, just log and continue

    async def _execute_single_workflow(
        self,
        name: str,
        workflow: Dict[str, Any]
    ) -> None:
        """Execute a single workflow with proper error handling."""
        start_time = datetime.now()
        try:
            # Execute workflow function
            result = await workflow['workflow_func'](workflow['config'])
            
            # Update status
            self.workflow_statuses[name] = {
                'status': 'success',
                'start_time': start_time,
                'end_time': datetime.now(),
                'result': result
            }
            
        except Exception as e:
            self.logger.error(f"Error in workflow {name}: {str(e)}")
            self.workflow_statuses[name] = {
                'status': 'failed',
                'start_time': start_time,
                'end_time': datetime.now(),
                'error': str(e)
            }
            raise

    def get_workflow_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific workflow."""
        return self.workflow_statuses.get(name)

    def get_all_workflow_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get the status of all workflows."""
        return self.workflow_statuses

    def stop_continuous_load(self) -> None:
        """Stop the continuous load execution."""
        self._stop_event.set()

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop_continuous_load()
        self.executor.shutdown(wait=True) 