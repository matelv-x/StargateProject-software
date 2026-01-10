"""
Async web server using FastAPI that serves both static files and API endpoints.
Runs in its own thread with an async event loop to avoid blocking other operations.
"""
import os
import asyncio
import collections
import platform
from fastapi import FastAPI, Request, HTTPException, Query, APIRouter, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from threading import Thread


class StargateWebServerAsync:
    """
    Async web server using FastAPI that serves both static files and API endpoints.
    Runs in its own thread with an async event loop to avoid blocking other operations.
    """

    def __init__(self, stargate, base_path, port):
        self.stargate = stargate
        self.base_path = base_path
        self.port = port
        self.app = FastAPI(title="Stargate Control API")
        self.server_thread = None
        self.server = None

        # Setup CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Create API router with /stargate prefix for backward compatibility
        self.api_router = APIRouter(prefix="/stargate")
        
        # Setup routes (API routes only, no catch-all)
        self._setup_routes()
        
        # Include the router in the app BEFORE registering catch-all routes
        self.app.include_router(self.api_router)

        # Setup static file serving (catch-all route, must be last, AFTER router is included)
        web_dir = os.path.join(self.base_path, 'web')
        self.web_dir = web_dir if os.path.isdir(web_dir) else None
        self._setup_static_routes()

    def _register_route(self, method, path, handler):
        """Register a route on both the API router (with /stargate prefix) and the app (without prefix)"""
        if method == "get":
            self.api_router.get(path)(handler)
            self.app.get(path)(handler)
        elif method == "post":
            self.api_router.post(path)(handler)
            self.app.post(path)(handler)

    def _setup_routes(self):
        """Configure all API routes"""
        # Routes are defined on self.api_router which has /stargate prefix
        # Also define routes on self.app without prefix for direct access

        # ========== GET ENDPOINTS ==========
        # Define routes on both router (with /stargate prefix) and app (without prefix)

        async def get_is_alive():
            return {"is_alive": True}
        self.api_router.get("/get/is_alive")(get_is_alive)
        self.app.get("/get/is_alive")(get_is_alive)

        async def get_address_book(type: str = Query("all", alias="type")):
            data = {}
            if type == "standard":
                data['address_book'] = self.stargate.addr_manager.get_book().get_standard_gates()
            elif type == "fan":
                data['address_book'] = self.stargate.addr_manager.get_book().get_fan_and_lan_addresses()
            else:
                all_addr = self.stargate.addr_manager.get_book().get_all_nonlocal_addresses()
                data['address_book'] = dict(sorted(all_addr.items()))

            data['summary'] = self.stargate.addr_manager.get_summary_from_book(data['address_book'], True)
            data['galaxy_path'] = self.stargate.galaxy_path
            return data
        self._register_route("get", "/get/address_book", get_address_book)

        async def get_local_address():
            return self.stargate.addr_manager.get_book().get_local_address()
        self._register_route("get", "/get/local_address", get_local_address)

        async def get_dialing_status():
            return {
                "gate_name": self.stargate.addr_manager.get_book().get_local_gate_name(),
                "local_address": self.stargate.addr_manager.get_book().get_local_address(),
                "address_buffer_outgoing": self.stargate.address_buffer_outgoing,
                "locked_chevrons_outgoing": self.stargate.locked_chevrons_outgoing,
                "address_buffer_incoming": self.stargate.address_buffer_incoming,
                "locked_chevrons_incoming": self.stargate.locked_chevrons_incoming,
                "wormhole_active": self.stargate.wormhole_active,
                "black_hole_connected": self.stargate.black_hole,
                "connected_planet": self.stargate.connected_planet_name,
                "wormhole_open_time": self.stargate.wh_manager.open_time,
                "wormhole_max_time": self.stargate.wh_manager.wormhole_max_time,
                "wormhole_time_till_close": self.stargate.wh_manager.get_time_remaining(),
                "ring_position": self.stargate.ring.get_position(),
                "speed_dial_full_address": self.stargate.cfg.get('dialing_address_book_dials_full_address')
            }
        self._register_route("get", "/get/dialing_status", get_dialing_status)

        async def get_system_info():
            data = {
                "gate_name": self.stargate.addr_manager.get_book().get_local_gate_name(),
                "local_stargate_address": self.stargate.addr_manager.get_book().get_local_address(),
                "local_stargate_address_string": self.stargate.addr_manager.get_book().get_local_address_string(),
                "subspace_public_key": self.stargate.subspace_client.get_public_key(),
                "subspace_ip_address_config": self.stargate.subspace_client.get_configured_ip(),
                "subspace_ip_address_active": self.stargate.net_tools.get_subspace_ip(True),
                "lan_ip_address": self.stargate.net_tools.get_ip_by_interface_list(['wlan0', 'eth0', 'en0', 'en1']),
                "software_version": str(self.stargate.sw_updater.get_current_version()),
                "software_update_last_check": self.stargate.cfg.get('software_update_last_check'),
                "software_update_status": self.stargate.cfg.get('software_update_status'),
                "python_version": platform.python_version(),
                "internet_available": self.stargate.net_tools.has_internet_access(),
                "subspace_available": self.stargate.subspace_client.is_online(),
                "standard_gate_count": len(self.stargate.addr_manager.get_book().get_standard_gates()),
                "fan_gate_count": len(self.stargate.addr_manager.get_book().get_fan_gates()),
                "lan_gate_count": len(self.stargate.addr_manager.get_book().get_lan_gates()),
                "fan_gate_last_update": self.stargate.cfg.get('fan_gate_last_update'),
                "dialer_mode": self.stargate.dialer.type,
                "hardware_mode": self.stargate.electronics.name,
                "audio_volume": self.stargate.audio.volume,
                "galaxy": self.stargate.galaxy
            }
            # Add lifetime stats
            for key, value in self.stargate.dialing_log.get_summary().items():
                data['stats_'+key] = value.get('value')
            return data
        self._register_route("get", "/get/system_info", get_system_info)

        async def get_hardware_status():
            return {
                "chevrons": self.stargate.chevrons.get_status(),
                "glyph_ring": self.stargate.ring.get_status()
            }
        self._register_route("get", "/get/hardware_status", get_hardware_status)

        async def get_dhd_symbols():
            return self.stargate.symbol_manager.get_dhd_symbols()
        self._register_route("get", "/get/dhd_symbols", get_dhd_symbols)

        async def get_symbols():
            return {
                "symbols": self.stargate.symbol_manager.get_all_ddslick()
            }
        self._register_route("get", "/get/symbols", get_symbols)

        async def get_symbols_all():
            return self.stargate.symbol_manager.get_all()
        self._register_route("get", "/get/symbols_all", get_symbols_all)

        async def get_config():
            return collections.OrderedDict(sorted(self.stargate.cfg.get_all_configs().items()))
        self._register_route("get", "/get/config", get_config)

        async def get_audio_clips():
            return self.stargate.audio.list_clips()
        self._register_route("get", "/get/audio_clips", get_audio_clips)

        # ========== POST ENDPOINTS ==========

        async def do_shutdown():
            self.stargate.wormhole_active = False
            await asyncio.sleep(5)
            os.system('systemctl poweroff')
            return {"success": True}
        self._register_route("post", "/do/shutdown", do_shutdown)

        async def do_reboot():
            self.stargate.wormhole_active = False
            await asyncio.sleep(5)
            os.system('systemctl reboot')
            return {"success": True}
        self._register_route("post", "/do/reboot", do_reboot)

        async def do_restart():
            if not self.stargate.app.is_daemon:
                return {"success": False, "message": "Software Reboot Requested, but not running as Daemon. Unable."}

            self.stargate.wormhole_active = False
            await asyncio.sleep(5)
            os.system('systemctl restart stargate.service')
            return {"success": True}
        self._register_route("post", "/do/restart", do_restart)

        async def do_chevron_cycle(request: Request):
            data = await request.json()
            self.stargate.chevrons.get(int(data['chevron_number'])).cycle_outgoing()
            return {"success": True}
        self._register_route("post", "/do/chevron_cycle", do_chevron_cycle)

        async def do_all_chevron_leds_off():
            self.stargate.chevrons.all_off()
            self.stargate.wormhole_active = False
            return {"success": True}
        self._register_route("post", "/do/all_chevron_leds_off", do_all_chevron_leds_off)

        async def do_all_chevron_leds_on():
            self.stargate.chevrons.all_lights_on()
            return {"success": True}
        self._register_route("post", "/do/all_chevron_leds_on", do_all_chevron_leds_on)

        async def do_wormhole_on():
            if not self.stargate.wormhole_active:
                self.stargate.wormhole_active = True
                return {"success": True}
            return {"success": False, "message": "A wormhole is already established."}
        self._register_route("post", "/do/wormhole_on", do_wormhole_on)

        async def do_wormhole_off():
            self.stargate.wormhole_active = False
            return {"success": True}
        self._register_route("post", "/do/wormhole_off", do_wormhole_off)

        async def do_symbol_forward():
            self.stargate.ring.move(33, self.stargate.ring.forward_direction)
            self.stargate.ring.release()
            return {"success": True}
        self._register_route("post", "/do/symbol_forward", do_symbol_forward)

        async def do_symbol_backward():
            self.stargate.ring.move(33, self.stargate.ring.backward_direction)
            self.stargate.ring.release()
            return {"success": True}
        self._register_route("post", "/do/symbol_backward", do_symbol_backward)

        async def do_volume_down():
            self.stargate.audio.volume_down()
            return {"success": True}
        self._register_route("post", "/do/volume_down", do_volume_down)

        async def do_volume_up():
            self.stargate.audio.volume_up()
            return {"success": True}
        self._register_route("post", "/do/volume_up", do_volume_up)

        async def do_simulate_incoming():
            if not self.stargate.wormhole_active:
                # Get the loopback address and dial it
                for symbol_number in self.stargate.addr_manager.get_book().get_local_loopback_address():
                    self.stargate.address_buffer_incoming.append(symbol_number)

                self.stargate.address_buffer_incoming.append(7)  # Point of origin
                self.stargate.centre_button_incoming = True
                return {"success": True}
            return {"success": False, "message": "A wormhole is already established."}
        self._register_route("post", "/do/simulate_incoming", do_simulate_incoming)

        async def do_subspace_up():
            # API NOT IMPLEMENTED
            return {"success": False, "message": "API NOT IMPLEMENTED"}
        self._register_route("post", "/do/subspace_up", do_subspace_up)

        async def do_subspace_down():
            # API NOT IMPLEMENTED
            return {"success": False, "message": "API NOT IMPLEMENTED"}
        self._register_route("post", "/do/subspace_down", do_subspace_down)

        async def do_dhd_press(request: Request):
            data = await request.json()
            symbol_number = int(data.get('symbol', 0))

            if symbol_number > 0:
                self.stargate.keyboard.queue_symbol(symbol_number)
            elif symbol_number == 0:
                self.stargate.keyboard.queue_center_button()
            elif symbol_number == -1 and not self.stargate.wormhole_active and len(self.stargate.address_buffer_outgoing) > 0:
                # Abort dialing
                self.stargate.dialing_log.dialing_fail(self.stargate.address_buffer_outgoing)
                self.stargate.shutdown(cancel_sound=False, wormhole_fail_sound=False)

            return {"success": True}
        self._register_route("post", "/do/dhd_press", do_dhd_press)

        async def do_clear_outgoing_buffer():
            self.stargate.shutdown(cancel_sound=False, wormhole_fail_sound=False)
            return {"success": True}
        self._register_route("post", "/do/clear_outgoing_buffer", do_clear_outgoing_buffer)

        async def do_set_glyph_ring_zero():
            self.stargate.ring.zero_position()
            return {"success": True}
        self._register_route("post", "/do/set_glyph_ring_zero", do_set_glyph_ring_zero)

        async def do_dhd_test_enable():
            self.stargate.keyboard.enable_dhd_test(True)
            return {"success": True}
        self._register_route("post", "/do/dhd_test_enable", do_dhd_test_enable)

        async def do_dhd_test_disable():
            self.stargate.keyboard.enable_dhd_test(False)
            return {"success": True}
        self._register_route("post", "/do/dhd_test_disable", do_dhd_test_disable)

        async def do_audio_play(request: Request):
            try:
                data = await request.json()
                clip = data.get('clip')
                if not clip:
                    return {"success": False, "error": "Required fields missing or invalid request"}

                # Convert path into proper dictionary key
                clip_name = clip.replace('/', '_').split('.')[0]
                if clip_name[0] == '_':
                    clip_name = clip_name[1:]

                # Clip has not been initialized
                if clip_name not in self.stargate.audio.sounds:
                    self.stargate.audio.sounds[clip_name] = {'file': self.stargate.audio.init_wav_file('/' + clip)}

                self.stargate.audio.sound_start(clip_name)
                return {"success": True}
            except ValueError as ex:
                return {"success": False, "error": str(ex)}
        self._register_route("post", "/do/audio_play", do_audio_play)

        # ========== UPDATE ENDPOINTS ==========

        async def update_local_stargate_address(request: Request):
            try:
                data = await request.json()
                continue_to_save = True

                # Parse the address
                try:
                    address = [data['S1'], data['S2'], data['S3'], data['S4'], data['S5'], data['S6']]
                except KeyError:
                    return {"success": False, "error": "Required fields missing or invalid request"}

                # Validate that this is an acceptable address
                verify_avail, error, entry = self.stargate.addr_manager.verify_address_available(address)
                if verify_avail == "VERIFY_OWNED":
                    # This address is in use by a fan gate, but someone might be (re)configuring their own gate.
                    if not data.get('owner_confirmed'):
                        return {
                            "success": False,
                            "extend": "owner_unconfirmed",
                            "error": f"This address is in use by a Fan Gate - \"{entry['name']}\""
                        }
                elif verify_avail is False:
                    # This address is in use by a standard gate
                    return {"success": False, "error": error}

                # Store the address
                self.stargate.addr_manager.get_book().set_local_address(address)
                return {"success": True, "message": "There are no conflicts with your chosen address.<br><br>Local Address Saved."}

            except Exception as ex:
                if self.stargate.cfg.get("control_api_debug_enable"):
                    raise
                return {"success": False, "error": str(ex)}
        self._register_route("post", "/update/local_stargate_address", update_local_stargate_address)

        async def update_subspace_ip(request: Request):
            try:
                data = await request.json()
                self.stargate.subspace_client.set_ip_address(data['ip'])
                return {"success": True, "message": "Subspace IP Address Saved."}
            except ValueError as ex:
                return {"success": False, "message": str(ex)}
        self._register_route("post", "/update/subspace_ip", update_subspace_ip)

        async def update_config(request: Request):
            try:
                data = await request.json()
                message = self.stargate.cfg.set_bulk(data)
                return {"success": True, "message": "Configuration Saved", "results": message}
            except (NameError, ValueError) as ex:
                return {"success": False, "message": str(ex)}
        self._register_route("post", "/update/config", update_config)

        # Add logging middleware for debug mode
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            if self.stargate.cfg.get("control_api_debug_enable"):
                self.stargate.log.log(f'{request.client.host} {request.method} {request.url.path}')
            response = await call_next(request)
            return response

    def _setup_static_routes(self):
        """Setup static file serving routes - must be called AFTER router is included"""
        # Root path - serve index.htm
        @self.app.get("/")
        async def serve_root():
            """Serve index.htm for root path"""
            if not self.web_dir:
                raise HTTPException(status_code=404, detail="Static files directory not found")
            index_path = os.path.join(self.web_dir, "index.htm")
            if os.path.isfile(index_path):
                return FileResponse(index_path, media_type="text/html")
            raise HTTPException(status_code=404, detail="index.htm not found")

        # Catch-all route for static files (must be last, after all API routes)
        # CRITICAL: FastAPI matches routes in order, but path parameter routes can match before more specific routes
        # We use a route dependency to prevent this route from matching /stargate/ paths
        async def check_not_stargate_path(request: Request):
            """Dependency to prevent catch-all from matching /stargate/ paths"""
            full_path = str(request.url.path)
            if full_path.startswith("/stargate/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            return True
        
        @self.app.get("/{file_path:path}", dependencies=[Depends(check_not_stargate_path)])
        async def serve_static_files(file_path: str, request: Request):
            """Serve static files from the web directory"""
            # Also check file_path for other API patterns (without leading slash) as backup
            if file_path.startswith(("get/", "do/", "update/")):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            
            if not self.web_dir:
                raise HTTPException(status_code=404, detail="Static files directory not found")

            # Security: prevent directory traversal
            if ".." in file_path or file_path.startswith("/"):
                raise HTTPException(status_code=404, detail="File not found")

            full_path = os.path.join(self.web_dir, file_path)

            # Ensure the file is within the web directory
            if not os.path.abspath(full_path).startswith(os.path.abspath(self.web_dir)):
                raise HTTPException(status_code=404, detail="File not found")

            if not os.path.isfile(full_path):
                raise HTTPException(status_code=404, detail="File not found")

            # Determine content type
            content_type = "text/html"
            if file_path.endswith('.css'):
                content_type = 'text/css'
            elif file_path.endswith('.js'):
                content_type = 'application/javascript'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
            elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_path.endswith('.svg'):
                content_type = 'image/svg+xml'
            elif file_path.endswith('.ico'):
                content_type = 'image/x-icon'
            elif file_path.endswith('.json'):
                content_type = 'application/json'

            return FileResponse(full_path, media_type=content_type)

    def start(self):
        """Start the server in a separate thread"""
        def run_server():
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="info" if self.stargate.cfg.get("control_api_debug_enable") else "warning",
                loop="asyncio",
                access_log=self.stargate.cfg.get("control_api_debug_enable")
            )
            self.server = uvicorn.Server(config)
            loop.run_until_complete(self.server.serve())

        self.server_thread = Thread(target=run_server, daemon=True, name="stargate-async-web")
        self.server_thread.start()

    def shutdown(self):
        """Shutdown the server"""
        if self.server:
            self.server.should_exit = True

