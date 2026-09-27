"""Additive read-only Studio shell served from packaged web resources."""

from aiohttp import web

from irswitch.overlay.http import web_root


def register_studio_routes(app: web.Application) -> None:
    root = web_root() / "studio"

    async def redirect(_request: web.Request) -> web.Response:
        raise web.HTTPPermanentRedirect("/studio/")

    async def index(_request: web.Request) -> web.StreamResponse:
        path = root / "index.html"
        if not path.is_file():
            return web.Response(
                text="Studio build missing. Run pnpm install --frozen-lockfile and pnpm build in frontend/studio.",
                status=503,
            )
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})

    app.router.add_get("/studio", redirect)
    app.router.add_get("/studio/", index)
    assets = root / "assets"
    if assets.is_dir():
        app.router.add_static("/studio/assets/", assets, show_index=False)
