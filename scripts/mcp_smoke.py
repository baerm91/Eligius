"""Official SDK client smoke test against a running Remote MCP endpoint."""
import argparse
import asyncio
import json

from mcp import Client


async def main(url):
    async with Client(url, raise_exceptions=True, read_timeout_seconds=60) as client:
        tools = await client.list_tools()
        expected = {'search_objects', 'get_object', 'get_facets', 'get_distribution', 'get_statistics'}
        assert {tool.name for tool in tools.tools} == expected
        print('PASS official SDK connection; five read-only tools')
        first_id = None
        for name, arguments in [
            ('search_objects', {'filters': {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']}, 'page_size': 2}),
            ('get_facets', {'facet': 'Nominal', 'filters': {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']}}),
            ('get_distribution', {'dimension': 'Praegeherren', 'filters': {'Muenzstaette': ['Siscia']}, 'page_size': 2}),
            ('get_statistics', {'filters': {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']}}),
        ]:
            result = await client.call_tool(name, arguments)
            assert not result.is_error, result
            payload = result.structured_content
            if payload is None:
                payload = json.loads(result.content[0].text)
            print('PASS', name, json.dumps(payload, ensure_ascii=False)[:650])
            if name == 'search_objects' and payload.get('results'):
                first_id = payload['results'][0]['id']
        if not first_id:
            # A name in the corpus need not have the requested ruler role.
            result = await client.call_tool('search_objects', {'page_size': 1})
            payload = result.structured_content or json.loads(result.content[0].text)
            first_id = payload['results'][0]['id']
        result = await client.call_tool('get_object', {'object_id': first_id})
        assert not result.is_error
        print('PASS get_object', first_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url', help='Full HTTPS URL ending in /mcp')
    asyncio.run(main(parser.parse_args().url))
