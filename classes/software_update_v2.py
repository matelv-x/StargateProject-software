import subprocess
import sys
import os
import shutil

from collections import OrderedDict
from datetime import datetime
from packaging import version
import git
from git.exc import GitCommandError, InvalidGitRepositoryError
import rollbar

from network_tools import NetworkTools
from version import VERSION as current_version

class SoftwareUpdateV2:

    def __init__(self, app):

        self.app = app
        self.log = app.log
        self.cfg = app.cfg
        self.audio = app.audio
        self.current_version = current_version

        # Retrieve the configurations
        self.base_url = self.cfg.get("software_update_url")

        # Initialize the GitPython repo object
        self.repo = git.Repo('.')

        # Update the fan gates from the DB every x hours
        interval = self.cfg.get("software_update_interval")
        app.schedule.every(interval).hours.do( self.check_and_install )

    def get_current_version(self):
        """Returns the current software version."""
        return self.current_version

    def get_available_updates(self):
        """
        Checks for newer software versions from GitHub tags.
        Returns a sorted OrderedDict of available updates, with the latest version last.
        """
        try:
            # Configure git to ignore file permissions
            self.repo.config_writer().set_value("core", "fileMode", "false").release()

            # Explicitly fetch tags from remote
            self.log.log('Fetching tags from GitHub...')
            self.repo.remotes.origin.fetch(tags=True)

            # Parse current version for comparison
            current_version_sem = version.parse(self.current_version)
            newer_versions = {}

            # Loop over all tags and find newer versions
            for tag in self.repo.tags:
                try:
                    # Extract tag name more reliably
                    # tag.name gives us the tag name directly (e.g., "v4.0.0")
                    tag_name = str(tag.name)
                    # Remove 'v' prefix if present for version comparison
                    tag_version = tag_name.lstrip('v')

                    # Validate version format
                    version.parse(tag_version)  # Will raise if invalid

                    # Check if this version is newer than the current one
                    if version.parse(tag_version) > current_version_sem:
                        newer_versions[tag_version] = {
                            "tag_name": tag_name,
                            "tag_version": tag_version,
                            "tag_commit": str(tag.commit),
                            "tag_path": tag.path if hasattr(tag, 'path') else tag_name
                        }
                except (ValueError, version.InvalidVersion) as ex:
                    # Skip tags that don't follow version format
                    self.log.log(f"Skipping invalid tag format: {tag.name} ({ex})")
                    continue

            # Sort by version and return (latest will be last)
            return OrderedDict(sorted(newer_versions.items()))

        except GitCommandError as ex:
            self.log.log(f"Git error while fetching updates: {ex}")
            raise
        except Exception as ex:
            self.log.log(f"Unexpected error while fetching updates: {ex}")
            raise

    def _check_disk_space(self, required_mb=100):
        """Check if there's enough disk space (default 100MB). Returns True if sufficient."""
        try:
            stat = shutil.disk_usage(self.app.base_path)
            free_mb = stat.free / (1024 * 1024)
            if free_mb < required_mb:
                self.log.log(f"Insufficient disk space: {free_mb:.1f}MB free, need {required_mb}MB")
                return False
            return True
        except Exception as ex:
            self.log.log(f"Could not check disk space: {ex}")
            return True  # Assume OK if we can't check

    def _verify_tag_exists(self, tag_name):
        """Verify that the tag exists in the repository."""
        try:
            tag_ref = self.repo.tags[tag_name]
            return tag_ref is not None
        except (IndexError, KeyError):
            return False

    def do_update(self, version_config):
        """
        Performs the update to the specified version tag.
        Includes validation, proper git checkout, and verification.
        """
        tag_name = version_config.get('tag_name')
        tag_version = version_config.get('tag_version')
        tag_commit = version_config.get('tag_commit')

        message = f"Starting update from v{self.current_version} to v{tag_version}."
        self.log.log(message)

        # Pre-update validation
        try:
            # Check if repository is dirty
            if self.repo.is_dirty():
                self.log.log("!!!! Local copy of Gate has been modified, aborting update!")
                rollbar.report_message("Update Abort: Dirty Local Repo", 'warning')
                return

            # Verify internet connectivity
            if not NetworkTools(self.log).has_internet_access():
                self.log.log('No internet connection available. Aborting Software Update.')
                rollbar.report_message("Update Abort: No Internet", 'warning')
                return

            # Check disk space
            if not self._check_disk_space():
                self.log.log("Insufficient disk space. Aborting update.")
                rollbar.report_message("Update Abort: Insufficient Disk Space", 'warning')
                return

            # Fetch the specific tag to ensure it exists
            self.log.log(f'Fetching tag {tag_name} from remote...')
            self.repo.remotes.origin.fetch(tags=True, refspec=f'refs/tags/{tag_name}:refs/tags/{tag_name}')

            # Verify tag exists
            if not self._verify_tag_exists(tag_name):
                self.log.log(f"Tag {tag_name} not found in repository. Aborting update.")
                rollbar.report_message(f"Update Abort: Tag {tag_name} Not Found", 'error')
                return

            # Determine which branch to use (master or main)
            branch_name = None
            try:
                if not self.repo.head.is_detached:
                    branch_name = self.repo.active_branch.name
                else:
                    # If in detached HEAD, try to find master or main branch
                    for name in ['master', 'main']:
                        if name in self.repo.heads:
                            branch_name = name
                            break
                    if branch_name is None:
                        branch_name = 'master'  # Default to master
            except Exception as ex:
                self.log.log(f"Could not determine branch: {ex}. Using 'master'.")
                branch_name = 'master'

            # Update Rollbar
            rollbar.report_message(message, 'info')

            # Play a random update-related clip
            self.audio.play_random_clip("update")

            # Perform git checkout/reset to the tag
            self.log.log(f'Updating branch {branch_name} to tag {tag_name}...')
            try:
                # Ensure the branch exists, create it if it doesn't
                if branch_name not in self.repo.heads:
                    self.log.log(f'Creating branch {branch_name}...')
                    self.repo.create_head(branch_name)

                # Get the branch reference
                branch = self.repo.heads[branch_name]

                # Checkout the branch (if not already on it)
                need_checkout = False
                if self.repo.head.is_detached:
                    need_checkout = True
                elif self.repo.active_branch.name != branch_name:
                    need_checkout = True
                
                if need_checkout:
                    self.log.log(f'Checking out branch {branch_name}...')
                    self.repo.git.checkout(branch_name)

                # Reset the branch to the tag commit (hard reset)
                # This ensures we stay on a branch, not in detached HEAD state
                self.log.log(f'Resetting branch {branch_name} to tag {tag_name} (commit {tag_commit[:7]})...')
                branch.set_commit(tag_commit, 'hard')
                self.log.log(f'Successfully updated branch {branch_name} to tag {tag_name}')
            except GitCommandError as ex:
                self.log.log(f"Git checkout/reset failed: {ex}")
                rollbar.report_message(f"Update Failed: Git Checkout Error - {ex}", 'error')
                raise

            # Post-update verification
            current_commit = str(self.repo.head.commit)
            if current_commit != tag_commit:
                error_msg = f"Update verification failed: expected commit {tag_commit}, got {current_commit}"
                self.log.log(f"!!!! {error_msg}")
                rollbar.report_message(f"Update Failed: Verification Error - {error_msg}", 'error')
                return

            # Verify version.py matches expected version
            try:
                # Re-import version to get the new value after checkout
                import importlib
                import version as version_module
                importlib.reload(version_module)
                new_version = version_module.VERSION
                if new_version != tag_version:
                    self.log.log(f"Warning: version.py shows {new_version}, expected {tag_version}. Continuing anyway.")
            except Exception as ex:
                self.log.log(f"Could not verify version.py: {ex}. Continuing anyway.")

            # Run apt-get updates on Raspberry Pi
            if self.is_raspi():
                try:
                    self.log.log('Updating package lists...')
                    subprocess.check_call(["apt-get", "update"], timeout=300)
                except subprocess.TimeoutExpired:
                    self.log.log("apt-get update timed out, continuing anyway")
                except subprocess.CalledProcessError as ex:
                    self.log.log(f"apt-get update failed: {ex}, continuing anyway")

            # Run PIP requirements.txt update
            try:
                if self.is_raspi():
                    file_name = 'requirements.txt'
                else:
                    # OS lacks hardware support, install minimum requirements
                    file_name = 'requirements_minimum.txt'

                self.log.log(f'Installing Python dependencies from {file_name}...')
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "-r", os.path.join(self.app.base_path, file_name)],
                    timeout=600
                )
            except subprocess.TimeoutExpired:
                self.log.log("pip install timed out")
                rollbar.report_message("Update Warning: pip install timed out", 'warning')
            except subprocess.CalledProcessError as ex:
                self.log.log(f"pip install failed: {ex}")
                rollbar.report_message(f"Update Warning: pip install failed - {ex}", 'warning')

            # Wait for the clip to finish playing before restarting
            self.audio.random_clip_wait_done()

            self.log.log('Update installed successfully -> restarting the program')
            rollbar.report_message("Update Complete", 'info')

            self.app.restart()

        except GitCommandError as ex:
            self.log.log(f"Git error during update: {ex}")
            rollbar.report_message(f"Update Failed: Git Error - {ex}", 'error')
            self.cfg.set('software_update_exception', True)
            raise
        except InvalidGitRepositoryError as ex:
            self.log.log(f"Invalid git repository: {ex}")
            rollbar.report_message(f"Update Failed: Invalid Repository - {ex}", 'error')
            self.cfg.set('software_update_exception', True)
            raise
        except Exception as ex:
            self.log.log(f"Unexpected error during update: {ex}")
            rollbar.report_message(f"Update Failed: Unexpected Error - {ex}", 'error')
            self.cfg.set('software_update_exception', True)
            raise

    def check_and_install(self):
        """
        Checks for available updates and installs them one at a time, in order.
        This is called periodically based on the software_update_interval configuration.
        """
        try:
            # Verify that we have an internet connection
            if not NetworkTools(self.log).has_internet_access():
                self.log.log('No internet connection available. Aborting Software Update.')
                return

            self.log.log('Checking for software updates.')
            updates_available = self.get_available_updates()

            if len(updates_available) > 0:
                self.log.log(f"Found {len(updates_available)} available update(s)")

                # Get the next version to update to (first item in sorted dict - lowest version)
                # Updates are applied one at a time, in order
                next_version = list(updates_available.values())[0]
                most_recent_version = list(updates_available.values())[-1]
                next_tag_name = next_version.get('tag_name')
                most_recent_tag_name = most_recent_version.get('tag_name')

                self.cfg.set('software_update_status', f"Update Available (next): {most_recent_tag_name}")
                self.log.log(f"Next version to update: {next_tag_name} (latest available: {most_recent_tag_name})")

                rollbar.report_message(f"Update Available (next): {next_tag_name}", 'info')

                # Update to the next version (one at a time)
                self.do_update(next_version)
            else:
                self.log.log("The Stargate is up-to-date.")
                self.cfg.set('software_update_last_check', str(datetime.now()))
                self.cfg.set('software_update_status', 'up-to-date')
                self.cfg.set('software_update_exception', False)

        except GitCommandError as ex:
            self.log.log(f"Git error during update check: {ex}")
            self.cfg.set('software_update_last_check', str(datetime.now()))
            self.cfg.set('software_update_exception', True)
            rollbar.report_message(f"Update Check Failed: Git Error - {ex}", 'error')
        except InvalidGitRepositoryError as ex:
            self.log.log(f"Invalid git repository: {ex}")
            self.cfg.set('software_update_last_check', str(datetime.now()))
            self.cfg.set('software_update_exception', True)
            rollbar.report_message(f"Update Check Failed: Invalid Repository - {ex}", 'error')
        except Exception as ex:  # pylint: disable=broad-except
            self.log.log(f"Software update failed with error: {ex}")
            self.cfg.set('software_update_last_check', str(datetime.now()))
            self.cfg.set('software_update_exception', True)
            rollbar.report_message(f"Update Check Failed: {ex}", 'error')

    @staticmethod
    def is_raspi():
        # Is an ARM processor, and not Apple Silicon M1 (also ARM)
        return os.uname()[4][:3] == 'arm' and "Darwin" not in os.uname().sysname
