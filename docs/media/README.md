# Product previews

- `dictation.gif`: the website's Linear → Gmail → ChatGPT demonstration, recorded from rendered browser frames. Text appears as one result, and the recording bars follow the demo's reference levels.
- `first-dictation.gif`: the actual app UI with `tools/demo_server.py --practice`, showing the empty field, listening, thinking, result, Continue and Home. Backend phases use a timed example, not a microphone recording.

Both GIFs use example data and contain no personal recordings or account information. Captured frame timing is retained; duplicate frames are combined without shortening their pauses. The previews have no animated fake cursor.

To recreate the second preview, run `python tools/demo_server.py --practice`, open its printed loopback URL, and capture the rendered frames through the first dictation and Continue. The website preview uses `site/index.html` served locally. `tools/make_product_gif.py FRAME_DIRECTORY OUTPUT.gif` assembles JPEG frames and a `timing.json` list of `{file, at_ms}` entries into a GIF with a shared palette.
