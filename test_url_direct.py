#!/usr/bin/env python
from offline_gis_app.server_ingestion.services.tile_url_builder import build_xyz_url

url = build_xyz_url(r'C:\Users\Jitaditya Ray\common_project\data_test\dem.tif')
print('Built URL:')
print(url)
print()
print('URL decoded (for reference):')
from urllib.parse import unquote
parts = url.split('?')
if len(parts) == 2:
    base, query = parts
    print('Base:', base)
    print('Query:', query)
    params = query.split('&')
    for param in params:
        k, v = param.split('=', 1)
        print(f'  {k}={unquote(v)}')
