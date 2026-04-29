import httpx
import json

async def get_ids():
    digests = {
        "Daily": "6oJKonSZtTpDm3CNWk5YcjaP7SMriHNi7ae9recZZemD",
        "Weekly": "5heoPN9V9HGWHQNQTeengJiBB5muAzhL6wrJ21qg5b6K",
        "Monthly": "GEEGFhPvTXFSrFyWnDN9DiCWQqg5ZEaCaLpv2wQoGei8"
    }
    
    url = "https://fullnode.mainnet.sui.io"
    
    for name, digest in digests.items():
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sui_getTransactionBlock",
            "params": [
                digest,
                {"showEffects": True}
            ]
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if "result" in data and "effects" in data["result"]:
                    created = data["result"]["effects"].get("created", [])
                    for obj in created:
                        print(f"{name} Pool ID: {obj['reference']['objectId']}")
        except Exception as e:
            print(f"Error fetching {name}: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(get_ids())
