import asyncio
import aiosqlite

async def fix():
    db = await aiosqlite.connect("data/moderator.db")
    await db.execute(
        "UPDATE campaigns SET tweet_url=?, status='active' WHERE campaign_id='skills'",
        ("https://x.com/AlyAttaran/status/2038304408866267180",)
    )
    await db.commit()
    cursor = await db.execute("SELECT campaign_id, status, tweet_url FROM campaigns")
    rows = await cursor.fetchall()
    for r in rows:
        print(f"Campaign: {r[0]}, status: {r[1]}, url: {r[2]}")
    await db.close()

asyncio.run(fix())
