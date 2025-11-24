#!/bin/bash
# Setup SSH key if mounted
# Support multiple mount locations
MOUNTED_PRIVATE_KEY_ALT="/secrets/id_rsa"
MOUNTED_PRIVATE_KEY="/home/krkn/.ssh/id_rsa"
MOUNTED_PUBLIC_KEY="/home/krkn/.ssh/id_rsa.pub"
WORKING_KEY="/home/krkn/.ssh/id_rsa.key"

# Determine which source to use
SOURCE_KEY=""
if [ -f "$MOUNTED_PRIVATE_KEY_ALT" ]; then
    SOURCE_KEY="$MOUNTED_PRIVATE_KEY_ALT"
    echo "Found SSH key at alternative location: $SOURCE_KEY"
elif [ -f "$MOUNTED_PRIVATE_KEY" ]; then
    SOURCE_KEY="$MOUNTED_PRIVATE_KEY"
    echo "Found SSH key at default location: $SOURCE_KEY"
fi

# Setup SSH private key and create config for outbound connections
if [ -n "$SOURCE_KEY" ]; then
    echo "Setting up SSH private key from: $SOURCE_KEY"

    # Check current permissions and ownership
    ls -la "$SOURCE_KEY"

    # Since the mounted key might be owned by root and we run as krkn user,
    # we cannot modify it directly. Copy to a new location we can control.
    echo "Copying SSH key to working location: $WORKING_KEY"

    # Try to copy - if readable by anyone, this will work
    if cp "$SOURCE_KEY" "$WORKING_KEY" 2>/dev/null || cat "$SOURCE_KEY" > "$WORKING_KEY" 2>/dev/null; then
        chmod 600 "$WORKING_KEY"
        echo "SSH key copied successfully"
        ls -la "$WORKING_KEY"

        # Verify the key is readable
        if ssh-keygen -y -f "$WORKING_KEY" > /dev/null 2>&1; then
            echo "SSH private key verified successfully"
        else
            echo "Warning: SSH key verification failed, but continuing anyway"
        fi

        # Create SSH config to use the working key
        cat > /home/krkn/.ssh/config <<EOF
Host *
    IdentityFile $WORKING_KEY
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
        chmod 600 /home/krkn/.ssh/config
        echo "SSH config created with default identity: $WORKING_KEY"
    else
        echo "ERROR: Cannot read SSH key at $SOURCE_KEY"
        echo "Key is owned by: $(stat -c '%U:%G' "$SOURCE_KEY" 2>/dev/null || stat -f '%Su:%Sg' "$SOURCE_KEY" 2>/dev/null)"
        echo ""
        echo "Solutions:"
        echo "1. Mount with world-readable permissions (less secure): chmod 644 /path/to/key"
        echo "2. Mount to /secrets/id_rsa instead of /home/krkn/.ssh/id_rsa"
        echo "3. Change ownership on host: chown \$(id -u):\$(id -g) /path/to/key"
        exit 1
    fi
fi

# Setup SSH public key if mounted (for inbound server access)
if [ -f "$MOUNTED_PUBLIC_KEY" ]; then
    echo "SSH public key already present at $MOUNTED_PUBLIC_KEY"
    # Try to fix permissions (will fail silently if file is mounted read-only or owned by another user)
    chmod 600 "$MOUNTED_PUBLIC_KEY" 2>/dev/null
    if [ ! -f "/home/krkn/.ssh/authorized_keys" ]; then
        cp "$MOUNTED_PUBLIC_KEY" /home/krkn/.ssh/authorized_keys
        chmod 600 /home/krkn/.ssh/authorized_keys
    fi
fi
