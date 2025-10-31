#!/bin/bash
# Setup SSH key if mounted
MOUNTED_KEY="/home/krkn/.ssh/id_rsa.pub"

# Setup SSH private key and create config for outbound connections
if [ -f "$MOUNTED_KEY" ]; then
    echo "Setting up SSH private key from mounted location: $MOUNTED_KEY"
    chmod 600 "$MOUNTED_KEY"

    # Create SSH config to use this key by default for all hosts
    cat > /home/krkn/.ssh/config <<EOF
Host *
    IdentityFile $MOUNTED_KEY
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
    chmod 600 /home/krkn/.ssh/config
    echo "SSH config created with default identity: $MOUNTED_KEY"
fi

# Setup SSH public key if mounted (for inbound server access)
if [ -f "/tmp/ssh-publickey" ]; then
    echo "Setting up SSH public key from /tmp/ssh-publickey"
    cp /tmp/ssh-publickey /home/krkn/.ssh/authorized_keys
    chmod 600 /home/krkn/.ssh/authorized_keys
elif [ -f $MOUNTED_KEY ]; then
    echo "SSH public key already present at $MOUNTED_KEY"
    if [ ! -f "/home/krkn/.ssh/authorized_keys" ]; then
        cp /home/krkn/.ssh/id_rsa.pub /home/krkn/.ssh/authorized_keys
        chmod 600 /home/krkn/.ssh/authorized_keys
    fi
fi
