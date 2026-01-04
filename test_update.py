#!/usr/bin/env python3
"""
Standalone test script for testing the auto-update functionality.
This script allows testing the update logic without running the full application.

Usage:
    # Test with existing tags (set a lower version in version.py first)
    python3 test_update.py

    # Test with a specific version
    python3 test_update.py --version 3.9.0
"""

import sys
import os
import argparse

# Add classes to path
sys.path.append('classes')

from packaging import version
import git
from git.exc import GitCommandError


def test_get_available_updates(current_version_str):
    """Test the get_available_updates logic."""
    print(f"Testing with current version: {current_version_str}")
    print("=" * 60)
    
    try:
        repo = git.Repo('.')
        
        # Configure git to ignore file permissions
        repo.config_writer().set_value("core", "fileMode", "false").release()
        
        # Fetch tags from remote
        print("Fetching tags from GitHub...")
        repo.remotes.origin.fetch(tags=True)
        print("✓ Tags fetched successfully\n")
        
        # Parse current version for comparison
        current_version_sem = version.parse(current_version_str)
        newer_versions = {}
        
        print("Checking tags...")
        # Loop over all tags and find newer versions
        for tag in repo.tags:
            try:
                tag_name = str(tag.name)
                tag_version = tag_name.lstrip('v')
                
                # Validate version format
                version.parse(tag_version)  # Will raise if invalid
                
                # Check if this version is newer than the current one
                if version.parse(tag_version) > current_version_sem:
                    newer_versions[tag_version] = {
                        "tag_name": tag_name,
                        "tag_version": tag_version,
                        "tag_commit": str(tag.commit),
                    }
                    print(f"  ✓ Found newer version: {tag_name} (commit: {tag.commit.hexsha[:7]})")
            except (ValueError, version.InvalidVersion) as ex:
                print(f"  ⊗ Skipping invalid tag: {tag.name} ({ex})")
                continue
        
        if not newer_versions:
            print("\nNo newer versions found. Already up-to-date!")
            return None
        
        # Sort by version
        from collections import OrderedDict
        sorted_versions = OrderedDict(sorted(newer_versions.items()))
        
        print(f"\n{'=' * 60}")
        print(f"Found {len(sorted_versions)} newer version(s):")
        for idx, (v, info) in enumerate(sorted_versions.items(), 1):
            print(f"  {idx}. {info['tag_name']} (commit: {info['tag_commit'][:7]})")
        
        # Get the next version (first item - lowest)
        next_version = list(sorted_versions.values())[0]
        print(f"\nNext version to update to: {next_version['tag_name']}")
        print(f"Commit: {next_version['tag_commit']}")
        
        return next_version
        
    except GitCommandError as ex:
        print(f"✗ Git error: {ex}")
        return None
    except Exception as ex:
        print(f"✗ Unexpected error: {ex}")
        import traceback
        traceback.print_exc()
        return None


def test_checkout_logic(version_config, dry_run=True):
    """Test the checkout logic (dry run by default)."""
    print(f"\n{'=' * 60}")
    print(f"Testing checkout logic for: {version_config['tag_name']}")
    print(f"{'=' * 60}\n")
    
    try:
        repo = git.Repo('.')
        
        # Check if repository is dirty
        if repo.is_dirty():
            print("✗ Repository is dirty. Cannot test checkout.")
            return False
        
        tag_name = version_config['tag_name']
        tag_commit = version_config['tag_commit']
        
        # Verify tag exists
        if tag_name not in repo.tags:
            print(f"✗ Tag {tag_name} not found in repository")
            return False
        
        print(f"✓ Tag {tag_name} exists")
        print(f"✓ Tag commit: {tag_commit[:7]}")
        
        # Determine branch name
        branch_name = None
        if not repo.head.is_detached:
            branch_name = repo.active_branch.name
        else:
            for name in ['master', 'main']:
                if name in repo.heads:
                    branch_name = name
                    break
            if branch_name is None:
                branch_name = 'master'
        
        print(f"✓ Using branch: {branch_name}")
        
        if dry_run:
            print("\n[DRY RUN] Would perform the following:")
            print(f"  1. Ensure branch '{branch_name}' exists")
            print(f"  2. Checkout branch '{branch_name}' (if not already on it)")
            print(f"  3. Reset branch '{branch_name}' to commit {tag_commit[:7]} (hard reset)")
            print(f"  4. Verify commit matches {tag_commit[:7]}")
            print("\n✓ Dry run completed successfully!")
            return True
        else:
            print("\n[LIVE RUN] Performing checkout...")
            # This would actually do the checkout - be careful!
            print("⚠ LIVE RUN NOT IMPLEMENTED IN TEST SCRIPT FOR SAFETY")
            print("   Use actual software_update_v2.py for live testing")
            return False
            
    except Exception as ex:
        print(f"✗ Error: {ex}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description='Test auto-update functionality')
    parser.add_argument('--version', type=str, help='Current version to test with (e.g., 4.0.0a24)')
    parser.add_argument('--test-checkout', action='store_true', help='Also test checkout logic (dry run)')
    
    args = parser.parse_args()
    
    # Get current version
    if args.version:
        current_version = args.version
    else:
        # Read from version.py
        try:
            import version as version_module
            current_version = version_module.VERSION
        except ImportError:
            print("Error: Could not import version module")
            print("Please specify --version or ensure version.py exists")
            sys.exit(1)
    
    print("Auto-Update Functionality Test")
    print("=" * 60)
    
    # Test getting available updates
    next_version = test_get_available_updates(current_version)
    
    if next_version and args.test_checkout:
        # Test checkout logic (dry run)
        test_checkout_logic(next_version, dry_run=True)
    
    print("\n" + "=" * 60)
    print("Test completed!")
    if next_version:
        print(f"\nTo test with a real update, you could:")
        print(f"  1. Create a test tag: git tag -a v4.0.1-test -m 'Test tag'")
        print(f"  2. Push it: git push origin v4.0.1-test")
        print(f"  3. Temporarily lower version.py to trigger the update")
        print(f"  4. Run the actual software and watch the logs")


if __name__ == '__main__':
    main()
