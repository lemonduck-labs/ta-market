"""Wrap an artifact page in the skeleton the platform adds at publish time, for local runs."""
import os, sys
src, out = sys.argv[1], sys.argv[2]
page = open(src, encoding="utf-8").read()
skeleton = ('<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}'
            'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
            '<script src="mock.js"></script></head><body>')
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(skeleton + page + "</body></html>")
