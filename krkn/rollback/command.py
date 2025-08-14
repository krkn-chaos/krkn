import os
import logging
from typing import Optional, TYPE_CHECKING

from krkn.rollback.config import RollbackConfig
from krkn.rollback.handler import execute_rollback_version_files, cleanup_rollback_version_files



if TYPE_CHECKING:
    from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
    

def list_rollback(run_uuid: Optional[str]=None, scenario_type: Optional[str]=None):
    """
    List rollback version files in a tree-like format.
    
    :param cfg: Configuration file path
    :param run_uuid: Optional run UUID to filter by
    :param scenario_type: Optional scenario type to filter by
    :return: Exit code (0 for success, 1 for error)
    """
    logging.info("Listing rollback version files")

    versions_directory = RollbackConfig().versions_directory
    
    logging.info(f"Rollback versions directory: {versions_directory}")
    
    # Check if the directory exists first
    if not os.path.exists(versions_directory):
        logging.info(f"Rollback versions directory does not exist: {versions_directory}")
        return 0
    
    # List all directories and files
    try:
        # Get all run directories
        run_dirs = []
        for item in os.listdir(versions_directory):
            item_path = os.path.join(versions_directory, item)
            if os.path.isdir(item_path):
                # Apply run_uuid filter if specified
                if run_uuid is None or run_uuid in item:
                    run_dirs.append(item)
        
        if not run_dirs:
            if run_uuid:
                logging.info(f"No rollback directories found for run_uuid: {run_uuid}")
            else:
                logging.info("No rollback directories found")
            return 0
        
        # Sort directories for consistent output
        run_dirs.sort()
        
        print(f"\n{versions_directory}/")
        for i, run_dir in enumerate(run_dirs):
            is_last_dir = (i == len(run_dirs) - 1)
            dir_prefix = "└── " if is_last_dir else "├── "
            print(f"{dir_prefix}{run_dir}/")
            
            # List files in this directory
            run_dir_path = os.path.join(versions_directory, run_dir)
            try:
                files = []
                for file in os.listdir(run_dir_path):
                    file_path = os.path.join(run_dir_path, file)
                    if os.path.isfile(file_path):
                        # Apply scenario_type filter if specified
                        if scenario_type is None or file.startswith(scenario_type):
                            files.append(file)
                
                files.sort()
                for j, file in enumerate(files):
                    is_last_file = (j == len(files) - 1)
                    file_prefix = "    └── " if is_last_dir else "│   └── " if is_last_file else ("│   ├── " if not is_last_dir else "    ├── ")
                    print(f"{file_prefix}{file}")
                    
            except PermissionError:
                file_prefix = "    └── " if is_last_dir else "│   └── "
                print(f"{file_prefix}[Permission Denied]")
                
    except Exception as e:
        logging.error(f"Error listing rollback directory: {e}")
        return 1
    
    return 0


def execute_rollback(telemetry_ocp: "KrknTelemetryOpenshift", run_uuid: Optional[str]=None, scenario_type: Optional[str]=None):
    """
    Execute rollback version files and cleanup if successful.
    
    :param cfg: Configuration file path
    :param run_uuid: Optional run UUID to filter by
    :param scenario_type: Optional scenario type to filter by
    :return: Exit code (0 for success, 1 for error)
    """
    logging.info("Executing rollback version files")
    
    if not run_uuid:
        logging.error("run_uuid is required for execute-rollback command")
        return 1
    
    if not scenario_type:
        logging.warning("scenario_type is not specified, executing all scenarios in rollback directory")
    
    try:
        # Execute rollback version files
        logging.info(f"Executing rollback for run_uuid={run_uuid}, scenario_type={scenario_type or '*'}")
        execute_rollback_version_files(telemetry_ocp, run_uuid, scenario_type)
        
        # If execution was successful, cleanup the version files
        logging.info("Rollback execution completed successfully, cleaning up version files")
        cleanup_rollback_version_files(run_uuid, scenario_type)
        
        logging.info("Rollback execution and cleanup completed successfully")
        return 0
        
    except Exception as e:
        logging.error(f"Error during rollback execution: {e}")
        return 1
