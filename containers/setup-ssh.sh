#!/bin/bash
# Setup SSH key if mounted
if [ -f "/tmp/ssh-publickey" ]; then
    echo "Setting up SSH public key from /tmp/ssh-publickey"
    cp /tmp/ssh-publickey /home/krkn/.ssh/authorized_keys
    chmod 600 /home/krkn/.ssh/authorized_key
elif [ -f "/home/krkn/.ssh/id_rsa.pub" ]; then
    echo "SSH public key already present at /home/krkn/.ssh/id_rsa.pub"
    if [ ! -f "/home/krkn/.ssh/authorized_keys" ]; then
        cp /home/krkn/.ssh/id_rsa.pub /home/krkn/.ssh/authorized_keys
        chmod 600 /home/krkn/.ssh/authorized_keys
    fi
fi
