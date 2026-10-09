import pathlib
d = pathlib.Path(__file__).parent
html = (d / "shell.html").read_text(encoding="utf-8")
for marker, nome in (("/*__TOKENS__*/", "tokens.css"), ("/*__STYLES__*/", "styles.css"), ("/*__DATA__*/", "data.js"), ("/*__APP__*/", "app.js")):
    html = html.replace(marker, (d / nome).read_text(encoding="utf-8").replace("</script>", "<\\/script>"))
out = d.parent / "mockup-excluir.html"
out.write_text(html, encoding="utf-8")
print(out, len(html))
