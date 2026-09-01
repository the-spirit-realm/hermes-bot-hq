# Example Home

A complete pair, taken from a research bot that publishes after each morning
digest. Copy both files into a bot's profile to see the page render, then let the
bot take over `data.json`:

```bash
mkdir -p ~/.hermes/profiles/<bot>/home
cp schema.json data.json ~/.hermes/profiles/<bot>/home/
```

`schema.json` declares six widgets, two actions, and a composer. `data.json`
fills five of them and leaves one empty on purpose, so you can see how an
unfilled widget renders. Full reference: `../docs/home-contract.md`.
