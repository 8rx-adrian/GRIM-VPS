# GRIM-VPS Bot V1 🤖

A powerful Discord bot designed for managing Linux LXC containers and VPS instances directly from your Discord server. Developed with speed, efficiency, and ease of use in mind.

---

## 🚀 Installation & Setup Guide

Follow these step-by-step instructions to install and configure the bot on your Linux LXC container.

### Step 1: Clone the Repository
First, clone the repository to your local machine and navigate into the project directory:

```bash
git clone https://github.com/8rx-adrian/GRIM-VPS
cd GRIM-VPS



### Step 2: Configure the Bot
Open the config.json file and update the following required fields:
 1. **Discord Token:** Insert your Discord bot token.
 2. **Admin & Owner IDs:** Add the Discord User IDs for the Main Admin and Server Owner to grant them administrative control.
```json
{
  "token": "YOUR_DISCORD_BOT_TOKEN_HERE",
  "owner_id": "YOUR_OWNER_DISCORD_ID",
  "admin_ids": ["YOUR_ADMIN_DISCORD_ID"]
}

```
### Step 3: Format the Configuration File
Run the following command to ensure the emoji configuration formatting is correctly aligned within the system:
```bash
sed -i 's/^emojis": {/  "emojis": {/' config.json

```
### Step 4: Verify JSON Structure
Before launching the bot, verify that your config.json file is completely error-free and valid by running this Python check:
```bash
python3 -c "import json; json.load(open('config.json')); print('JSON OK')"

```
> 💡 **Note:** If the command prints JSON OK, your configuration is correct and ready to go!
> 
### Step 5: Start the Bot
Once the configuration is verified, launch the bot using the following command:
```bash
python3 main.py

```
## 🛠️ Credits & Authors
This project is proudly developed and maintained by:
 * **8rx**
 * **Baba totka**
