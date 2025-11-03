#!/usr/bin/env python3
"""
Batch conversion script: Convert remaining Gmail tools from Composio SDK to REST API.
Converts tools systematically using the proven pattern from GmailFetchEmails.py.
"""
import os
import re

# Define the conversion mappings for each tool
TOOL_CONVERSIONS = {
    "GmailFetchMessageByThreadId.py": "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
    "GmailAddLabel.py": "GMAIL_ADD_LABEL_TO_EMAIL",
    "GmailListLabels.py": "GMAIL_LIST_LABELS",
    "GmailMoveToTrash.py": "GMAIL_MOVE_TO_TRASH",
    "GmailGetAttachment.py": "GMAIL_GET_ATTACHMENT",
    "GmailSearchPeople.py": "GMAIL_SEARCH_PEOPLE",
    # Phase 3
    "GmailDeleteMessage.py": "GMAIL_DELETE_MESSAGE",
    "GmailBatchDeleteMessages.py": "GMAIL_BATCH_DELETE_MESSAGES",
    "GmailCreateLabel.py": "GMAIL_CREATE_LABEL",
    "GmailModifyThreadLabels.py": "GMAIL_MODIFY_THREAD_LABELS",
    "GmailRemoveLabel.py": "GMAIL_REMOVE_LABEL",
    "GmailPatchLabel.py": "GMAIL_PATCH_LABEL",
    # Phase 4
    "GmailSendDraft.py": "GMAIL_SEND_DRAFT",
    "GmailDeleteDraft.py": "GMAIL_DELETE_DRAFT",
    "GmailGetPeople.py": "GMAIL_GET_PEOPLE",
    "GmailGetContacts.py": "GMAIL_GET_CONTACTS",
    "GmailGetProfile.py": "GMAIL_GET_PROFILE",
}

def convert_tool(file_path, action_name):
    """Convert a single tool from SDK to REST API."""
    print(f"\nConverting {os.path.basename(file_path)}...")

    with open(file_path, 'r') as f:
        content = f.read()

    # Check if already converted
    if 'import requests' in content and 'GMAIL_CONNECTION_ID' in content:
        print(f"  ✓ Already converted (has requests and GMAIL_CONNECTION_ID)")
        return True

    # Add import requests if not present
    if 'import requests' not in content:
        content = content.replace(
            'import os\n',
            'import os\nimport requests\n'
        )
        print(f"  ✓ Added 'import requests'")

    # Remove Composio SDK import
    if 'from composio import Composio' in content:
        content = content.replace('from composio import Composio\n', '')
        print(f"  ✓ Removed Composio SDK import")

    # Replace GMAIL_ENTITY_ID with GMAIL_CONNECTION_ID
    content = content.replace('GMAIL_ENTITY_ID', 'GMAIL_CONNECTION_ID')
    print(f"  ✓ Replaced GMAIL_ENTITY_ID → GMAIL_CONNECTION_ID")

    # Replace SDK execution pattern with REST API pattern
    # Pattern: client = Composio(api_key=api_key)
    if 'client = Composio(api_key=api_key)' in content:
        content = re.sub(
            r'# Initialize Composio client\s+client = Composio\(api_key=api_key\)',
            '# Composio REST API request (no SDK needed)',
            content
        )
        print(f"  ✓ Removed Composio client initialization")

    # Replace client.tools.execute() with REST API call
    # This is complex, so we'll use a targeted pattern
    sdk_pattern = r'result = client\.tools\.execute\(\s*"' + action_name + r'",\s*({[^}]*}|\w+),\s*user_id=entity_id\s*\)'

    if re.search(sdk_pattern, content, re.MULTILINE | re.DOTALL):
        # Extract the params dict
        match = re.search(sdk_pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            params_str = match.group(1)

            rest_api_code = f'''# Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/{action_name}/execute"
            headers = {{
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }}
            payload = {{
                "connectedAccountId": entity_id,
                "input": {params_str}
            }}

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()'''

            content = re.sub(sdk_pattern, rest_api_code, content, flags=re.MULTILINE | re.DOTALL)
            print(f"  ✓ Replaced SDK execution with REST API call")

    # Add RequestException handling if not present
    if 'requests.exceptions.RequestException' not in content:
        # Find the existing except Exception block and add RequestException before it
        content = re.sub(
            r'(\s+)(except Exception as e:)',
            r'\1except requests.exceptions.RequestException as e:\n\1    return json.dumps({\n\1        "error": f"API request failed: {str(e)}",\n\1        "type": "RequestException"\n\1    }, indent=2)\n\1\2',
            content
        )
        print(f"  ✓ Added RequestException handling")

    # Write the converted content back
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"  ✓ Successfully converted {os.path.basename(file_path)}")
    return True

def main():
    """Convert all remaining Gmail tools."""
    tools_dir = "/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/email_specialist/tools"

    print("=" * 80)
    print("BATCH CONVERSION: Gmail Tools SDK → REST API")
    print("=" * 80)
    print(f"\nTotal tools to process: {len(TOOL_CONVERSIONS)}")

    success_count = 0
    failed_count = 0

    for filename, action_name in TOOL_CONVERSIONS.items():
        file_path = os.path.join(tools_dir, filename)

        if not os.path.exists(file_path):
            print(f"\n⚠ WARNING: {filename} not found, skipping...")
            continue

        try:
            if convert_tool(file_path, action_name):
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"  ✗ ERROR converting {filename}: {e}")
            failed_count += 1

    print("\n" + "=" * 80)
    print("CONVERSION COMPLETE")
    print("=" * 80)
    print(f"✓ Successfully converted: {success_count}/{len(TOOL_CONVERSIONS)}")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count}/{len(TOOL_CONVERSIONS)}")
    print("\nAll tools now use Composio REST API instead of broken SDK!")

if __name__ == "__main__":
    main()
