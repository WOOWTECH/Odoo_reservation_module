# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request


class DebugController(http.Controller):
    @http.route("/pos-self-debug/<config_id>", auth="public", website=True)
    def debug_self_order(self, config_id=None, access_token=None, **kwargs):
        """Debug controller to check what's happening with self-order access"""
        debug_info = {
            "config_id": config_id,
            "config_id_type": str(type(config_id)),
            "access_token_param": access_token,
            "kwargs": str(kwargs),
        }

        try:
            # Check if config_id is numeric
            is_numeric = config_id and config_id.isnumeric()
            debug_info["is_numeric"] = is_numeric

            if access_token:
                # First get the pos.config by id only
                all_configs = request.env["pos.config"].sudo().search([("id", "=", config_id)], limit=1)
                debug_info["config_by_id_only"] = str(all_configs)
                if all_configs:
                    debug_info["db_access_token"] = all_configs.access_token
                    debug_info["token_match"] = all_configs.access_token == access_token
                    debug_info["token_lengths"] = f"db={len(all_configs.access_token)}, param={len(access_token)}"

                pos_config_sudo = request.env["pos.config"].sudo().search([
                    ("id", "=", config_id), ('access_token', '=', access_token)], limit=1)
                debug_info["search_with_token"] = str(pos_config_sudo)
                debug_info["search_with_token_count"] = len(pos_config_sudo)
            else:
                pos_config_sudo = request.env["pos.config"].sudo().search([
                    ("id", "=", config_id)], limit=1)
                debug_info["search_without_token"] = str(pos_config_sudo)
                debug_info["search_without_token_count"] = len(pos_config_sudo)

            if pos_config_sudo:
                debug_info["self_ordering_mode"] = pos_config_sudo.self_ordering_mode
                debug_info["has_active_session"] = pos_config_sudo.has_active_session
                debug_info["stored_access_token"] = pos_config_sudo.access_token
                debug_info["self_ordering_default_user_id"] = str(pos_config_sudo.self_ordering_default_user_id)

                company = pos_config_sudo.company_id
                user = pos_config_sudo.self_ordering_default_user_id
                pos_config = pos_config_sudo.sudo(False).with_company(company).with_user(user)
                debug_info["pos_config_after_with_user"] = str(pos_config)
                debug_info["pos_config_bool"] = bool(pos_config)

        except Exception as e:
            debug_info["error"] = str(e)

        return request.make_response(
            json.dumps(debug_info, indent=2),
            headers=[('Content-Type', 'application/json')]
        )
