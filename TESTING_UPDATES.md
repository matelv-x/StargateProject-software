# Testing Auto-Update Functionality

This document describes several ways to test the auto-update functionality without creating tags on the master branch.

## Option 1: Use the Test Script (Recommended for Quick Testing)

A standalone test script is available to test the update logic without actually performing updates:

```bash
# Test with current version from version.py
python3 test_update.py

# Test with a specific version (to simulate being on an older version)
python3 test_update.py --version 4.0.0a20

# Also test checkout logic (dry run)
python3 test_update.py --version 4.0.0a20 --test-checkout
```

This script:
- Fetches tags from GitHub
- Finds newer versions
- Shows what would be updated
- Optionally tests checkout logic (dry run only)
- Does NOT perform any actual updates

## Option 2: Create Test Tags on a Test Branch

1. Create a test branch:
```bash
git checkout -b test/auto-update
```

2. Make a small commit (e.g., update version.py to a test version):
```bash
# Edit version.py to something like "4.0.0-test1"
git add version.py
git commit -m "Test version for auto-update testing"
```

3. Create test tags:
```bash
# Create a few test tags with version numbers
git tag -a v4.0.0-test1 -m "Test tag 1"
git tag -a v4.0.0-test2 -m "Test tag 2"
git tag -a v4.0.0-test3 -m "Test tag 3"
```

4. Push the branch and tags:
```bash
git push origin test/auto-update
git push origin v4.0.0-test1 v4.0.0-test2 v4.0.0-test3
```

5. **On your test Raspberry Pi**, clone the repo on this branch or modify the remote:
```bash
# Option A: Clone on the test branch
cd ~
git clone -b test/auto-update https://github.com/jonnerd154/StargateProject-software.git sg1_v4_test

# Option B: If already cloned, change remote temporarily
cd ~/sg1_v4
git remote set-url origin https://github.com/jonnerd154/StargateProject-software.git
git fetch origin test/auto-update
git checkout test/auto-update
git fetch origin --tags
```

6. Temporarily lower version.py on the test Pi to trigger updates:
```bash
# Edit version.py to something lower, like "4.0.0-test0"
sudo nano ~/sg1_v4/version.py
```

7. Run the software and watch for updates in the logs:
```bash
sudo journalctl -u stargate.service -f
```

## Option 3: Test with Existing Tags (No New Tags Needed)

If you have existing tags on master that are newer than your current version, you can temporarily lower your version number to test:

1. **On your test Raspberry Pi**, backup and modify version.py:
```bash
cd ~/sg1_v4
sudo cp version.py version.py.backup
sudo nano version.py  # Change to an older version like "4.0.0a20"
```

2. Run the software and watch logs:
```bash
sudo journalctl -u stargate.service -f
```

3. After testing, restore the original version:
```bash
sudo mv version.py.backup version.py
```

## Option 4: Local Testing (Without GitHub)

For testing the code logic without any network access:

1. Create a temporary directory with a test git repository:
```bash
mkdir /tmp/test_stargate_update
cd /tmp/test_stargate_update
git init
```

2. Copy your code files
3. Create test commits and tags
4. Modify the SoftwareUpdateV2 class to point to this local repo (temporarily)

## Option 5: Fork-Based Testing

1. Fork the repository on GitHub
2. Create test tags on your fork
3. Temporarily modify the remote URL on your test Pi:
```bash
cd ~/sg1_v4
git remote set-url origin https://github.com/YOUR_USERNAME/StargateProject-software.git
git fetch origin --tags
```

4. Test with the test tags on your fork
5. When done, restore the original remote:
```bash
git remote set-url origin https://github.com/jonnerd154/StargateProject-software.git
```

## Testing Checklist

When testing, verify:

- [ ] Update detection works (finds newer versions)
- [ ] Updates are applied one at a time (not jumping to latest)
- [ ] Repository stays on a branch (not detached HEAD)
- [ ] Version verification works
- [ ] Error handling works (test with dirty repo, no internet, etc.)
- [ ] Log messages are clear and informative
- [ ] Rollbar notifications are sent correctly
- [ ] Restart works after update

## Safety Tips

1. **Always test on a separate Pi or in a test environment first**
2. **Backup your working version before testing**
3. **Use a test branch or fork, not master**
4. **Monitor logs closely during first test**
5. **Have a recovery plan** (know how to manually restore if needed)

## Quick Recovery

If an update test goes wrong:

```bash
# Stop the service
sudo systemctl stop stargate.service

# Reset git to a known good state
cd ~/sg1_v4
git fetch origin
git reset --hard origin/master  # or your branch
git clean -fd

# Restore version.py if needed
# sudo nano version.py

# Restart the service
sudo systemctl start stargate.service
```
