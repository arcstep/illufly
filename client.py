import httpx
import asyncio

async def main():
    conversation_id = 'f5183dcc-50c1-46eb-a840-c3e94951a66f'
    async with httpx.AsyncClient() as client:
        url = f'http://localhost:8000/achat/{conversation_id}'
        headers = {'accept': 'text/event-stream'}
        data = {'question': '写一首14句儿歌'}

        try:
            response = await client.post(url, headers=headers, json=data, timeout=None)
            response.raise_for_status()  # 将引发HTTPError，如果状态码不是200 OK
            
            async for line in response.aiter_lines():
                if line:
                    print(line)
        except httpx.HTTPError as e:
            print(f"HTTP error occurred: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
