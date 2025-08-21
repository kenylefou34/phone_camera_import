#!/bin/bash

# Demande à l'utilisateur d'entrer le nom d'utilisateur SSH
# read -p "Enter the SSH username: " SSH_USER
# or
SSH_USER="ken" #hard coded user name

# Demande à l'utilisateur d'entrer l'adresse IP du téléphone
read -p "Enter the phone last IP address number: 192.168.1." PHONE_ID
# hardcoded part of ip address
PHONE_IP="192.168.1.$PHONE_ID"

# Demande à l'utilisateur d'entrer le chemin du dossier de destination local
read -p "Enter the local destination path: " DEST

DEST_UNSORTED_FOLDER="$DEST/unsorted/"

mkdir $DEST_UNSORTED_FOLDER

PHONE_HOME="/storage/emulated/0/"

echo "Choose what you want to get:"
echo "1. Camera data"
echo "2. Movies data"
echo "3. Pictures data"

while true; do
  read -p "Enter the option data to get from the phone (1-3): " OPTION_SOURCE_FOLDER
  if [[ "$OPTION_SOURCE_FOLDER" =~ ^[1-3]$ ]]; then
    break
  else
    echo "Invalid option. Please enter a number between 1 and 3."
  fi
done

case "$OPTION_SOURCE_FOLDER" in
  1)
    REMOTE_SOURCE_FOLDER="DCIM/Camera/"
    ;;
  2)
    REMOTE_SOURCE_FOLDER="Movies/"
    ;;
  3)
    REMOTE_SOURCE_FOLDER="Pictures/"
    ;;
esac

PHONE_SYNC_FOLDER_PATH="${PHONE_HOME}${REMOTE_SOURCE_FOLDER}"

echo "You chose option $OPTION_SOURCE_FOLDER => syncing from $PHONE_SYNC_FOLDER_PATH ..."

# Synchronisation des fichiers plus récents que le fichier témoin
PHONE_FLAG_TIMESTAMP_PATH="$PHONE_SYNC_FOLDER_PATH/.flagfile_timestamp"
PHONE_FILES_TO_SYNC_PATH="$PHONE_HOME/.files_to_rsync.txt"

echo "PHONE_SYNC_FOLDER_PATH=$PHONE_SYNC_FOLDER_PATH"
echo "PHONE_FLAG_TIMESTAMP_PATH=$PHONE_FLAG_TIMESTAMP_PATH"
echo "PHONE_FILES_TO_SYNC_PATH=$PHONE_FILES_TO_SYNC_PATH"

ssh -p 2222 "$SSH_USER@$PHONE_IP" "
  rm '$PHONE_FILES_TO_SYNC_PATH'
  find '$PHONE_SYNC_FOLDER_PATH' -type f -newer '$PHONE_FLAG_TIMESTAMP_PATH' -print0 > '$PHONE_FILES_TO_SYNC_PATH'
"

# Get listing files to sync from the phone
LOCAL_TMP_LIST="/tmp/files_to_sync_list.txt"
scp -P 2222 "$SSH_USER@$PHONE_IP:$PHONE_FILES_TO_SYNC_PATH" "$LOCAL_TMP_LIST"

# syncing files
rsync -avz --files-from=$LOCAL_TMP_LIST --from0 -e "ssh -p 2222" "$SSH_USER@$PHONE_IP:/" "$DEST_UNSORTED_FOLDER"

# cleaning
rm "$LOCAL_TMP_LIST"

ssh -p 2222 "$SSH_USER@$PHONE_IP" "
  rm '$PHONE_FLAG_TIMESTAMP_PATH' &&
  touch '$PHONE_FLAG_TIMESTAMP_PATH'
"

exec ./build/phone_camera_import -s "$DEST_UNSORTED_FOLDER" -d "$DEST" --remove-copied

echo "Sync completed."

