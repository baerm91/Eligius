"""Read-only HTTPS/HTTP parity check between WebMCP JSON and Remote MCP."""
import argparse
import asyncio
import json

import httpx2
from mcp import Client


async def main(base):
    base = base.rstrip('/')
    async with httpx2.AsyncClient(timeout=60) as http, Client(base + '/mcp', raise_exceptions=True) as remote:
        manifest_response = await http.get(base + '/api/webmcp/manifest/')
        manifest_response.raise_for_status()
        manifest = manifest_response.json()
        schemas = {t.name: t.input_schema for t in (await remote.list_tools()).tools}
        assert schemas == {t['name']: t['inputSchema'] for t in manifest['data_tools']}
        print('PASS five identical Remote/WebMCP schemas; six UI/context tools')
        filters = {'Praegeherren': ['Valens']}
        first = await http.post(base + '/api/webmcp/data/search_objects/', json={'filters': filters, 'page_size': 1})
        first.raise_for_status()
        object_id = first.json()['results'][0]['id']
        for name, args in [
            ('search_objects', {'filters': filters, 'page_size': 25, 'page': 2}),
            ('get_object', {'object_id': object_id}),
            ('get_facets', {'facet': 'Nominal', 'filters': filters}),
            ('get_distribution', {'dimension': 'Muenzstaette', 'filters': filters}),
            ('get_statistics', {'filters': filters}),
        ]:
            result = await remote.call_tool(name, args)
            payload = result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)
            response = await http.post(base + '/api/webmcp/data/' + name + '/', json=args)
            response.raise_for_status()
            assert response.json() == payload, name
            print('PASS Remote/WebMCP result equality:', name)
        response = await http.post(base + '/api/webmcp/navigation/set_browse_filters/', json={
            'filters': {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia'], 'unbestimmt': False}})
        response.raise_for_status()
        url = response.json()['url']
        assert url == '/browse/?Praegeherren=Valens&Muenzstaette=Siscia&unbestimmt=False'
        print('PASS canonical Browse URL:', url)
        response = await http.post(base + '/api/webmcp/data/search_objects/', json={'filters': {'Typ__workflow': 1}})
        assert response.status_code == 400
        print('PASS forbidden filter rejected')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base_url')
    asyncio.run(main(parser.parse_args().base_url))
