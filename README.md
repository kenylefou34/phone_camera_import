Here’s how to use **SimpleSSHD** on Android to synchronize your files with rsync from Linux:

***

### 1. Install SimpleSSHD on Your Phone

- Download the SimpleSSHD from [F-Droid](https://f-droid.org/F-Droid.apk) app (you may have to update the app after launching it), also available in the resource folder of this project.
- Install it as usual (no root required).


### 2. Configure SimpleSSHD

- Open the app and go to the settings.
- The default SSH port is **2222**; leave it or change it if you want.
- Optionally: in "Home Directory," set the path you want to share (e.g., `/storage/emulated/0/Download/` for the "Download" folder).
- You can enable "Start on boot" or "Start on Open" as you prefer.
- You can disable entering password for each ssh request, see section 8. 

### 3. Start the SSH Server

- On your phone, tap "Start."
- Your local network IP (WiFi) appears at the top; note it to connect.


### 4. Connect via SSH

- From your Linux PC, connect using:

```bash
ssh -p 2222 username@PHONE_IP_ADDRESS
```

    - Replace `username` with the one shown on your phone, if provided, else choose one.
    - The initial password is shown on your phone screen; you can later set up your SSH public key for secure and convenient login.


### 5. Sync With rsync

- To copy files with rsync:

```bash
rsync -avz -e "ssh -p 2222" username@PHONE_IP_ADDRESS:/storage/emulated/0/Download/ /path/to/destination/on-PC/
```

    - Adjust the source and destination paths as needed.


### 6. Secure Your Access (Optional but Recommended)

- Add your SSH public key to the `authorized_keys` file on your phone so you don’t have to enter a password every time.


### 7. Bash script 

- A script named `run_backup.sh` handle synchronization steps (4 & 5).

### 8. Example to transfer your public key:

- In `SimmpleSSHD` app `Setting`, `SSH Path`, select the path you choose for example `/storage/emulated/0/.ssh/`.

```bash
scp -P 2222 /storage/emulated/0/.ssh/id_rsa.pub "$SSH_USER@$PHONE_IP:/storage/emulated/0/Download/id_rsa.pub"
```

- Here, `-P 2222` specifies the SSH port used by SimpleSSHD.
- The file is copied to the phone’s `Download` folder, for example.
- You can then point SimpleSSHD to this path as the `authorized_keys` file or copy this file to the correct location on the phone.

### 8.1. Then, to install your key in the remote `authorized_keys` file (if necessary):

1. Connect via SSH with password:
```bash
ssh -p 2222 "$SSH_USER@$PHONE_IP"
```

2. In the remote session, create the `.ssh` directory if needed and append the public key:
```bash
cat /storage/emulated/0/Download/id_rsa.pub >> ~/.ssh/authorized_keys
chmod 700 /storage/emulated/0/.ssh
chmod 600 /storage/emulated/0/.ssh/authorized_keys
```

3. Exit the session and try reconnecting via SSH — this time without a password prompt.

This method works to automate SSH connections (and thus rsync, scp, etc.) with SimpleSSHD, so you don’t have to enter your password every time.

***

**Notes:**

- SimpleSSHD only grants access to folders for which it has permission (usually internal storage, sometimes the SD card depending on Android version).
- Transfers occur over WiFi, so your PC and phone must be on the same local network.

This setup allows you to easily sync files between your Android phone and Linux PC, taking full advantage of rsync’s speed and reliability over SSH.

