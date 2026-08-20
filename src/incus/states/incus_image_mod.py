"""Salt state functions for managing Incus images."""

from incus.utils import log_state_changes

__virtualname__ = "incus"


def __virtual__():
    """Load when the Incus image execution functions are available."""
    if "incus.image_list" in __salt__:
        return __virtualname__
    return False, "incus image execution functions are not available"


def _get_alias_info(alias_name):
    """
    Get alias information using incus.image_alias_get.
    Returns alias dict or None if not found.
    """
    result = __salt__["incus.image_alias_get"](alias_name)
    if result.get("success"):
        return result.get("alias")
    return None


def _find_image_by_alias(alias_name):
    """
    Find image fingerprint by alias using incus.image_alias_get.
    Returns fingerprint or None if not found.
    """
    alias_info = _get_alias_info(alias_name)
    if alias_info:
        return alias_info.get("target")
    return None


# ======================================================================
# Image States
# ======================================================================


@log_state_changes
def image_present(
    name,
    fingerprint=None,
    source=None,
    public=None,
    auto_update=None,
    aliases=None,
    properties=None,
    expires_at=None,
    compression_algorithm=None,
):
    """
    Ensure an Incus image exists and matches all specified parameters.

    The state name (name parameter) is ALWAYS used as the primary alias for the image.
    Additional aliases can be specified via the 'aliases' parameter.

    :param name: State name - ALWAYS becomes an alias for the image
    :param fingerprint: Image fingerprint for exact search
    :param source: Import source (dict with server/alias or file path)
    :param public: Public access to image
    :param auto_update: Automatic image update
    :param aliases: List of additional aliases (name is always included)
    :param properties: Image properties
    :param expires_at: Expiration time (ISO 8601)
    :param compression_algorithm: Compression algorithm

    Image search logic:
      1. By fingerprint (if specified) - most accurate method
      2. By name alias (via API)
      3. By any alias in the aliases list
      4. By source.alias (for remote imports)

    Fields supported for reconciliation:
      - public
      - auto_update
      - aliases (name + additional aliases)
      - properties
      - expires_at
      - compression_algorithm

    Example:

    .. code-block:: yaml

        ubuntu2204:
          incus.image_present:
            - source:
                server: https://images.linuxcontainers.org
                alias: ubuntu/22.04
                protocol: simplestreams
            - auto_update: True
            - aliases:
                - ubuntu-latest
                - ubuntu-lts

        my-custom-image:
          incus.image_present:
            - source: /tmp/rootfs.tar.xz
            - public: True
            - aliases:
                - custom-base
                - app-template
    """

    ret = {
        "name": name,
        "result": True,
        "changes": {},
        "comment": "",
    }

    # ============================
    # 1. Build complete alias list
    # ============================
    # Name is ALWAYS the primary alias
    desired_aliases = [name]

    # Add additional aliases if provided
    if aliases:
        for a in aliases:
            if a not in desired_aliases:
                desired_aliases.append(a)

    # ============================
    # 2. Search for existing image
    # ============================
    image_match = None

    # Get list of images
    images = __salt__["incus.image_list"](recursion=1)
    if not images.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to list images: {images.get('error')}"
        return ret

    existing_images = images.get("images", [])

    # Search by fingerprint (highest priority)
    if fingerprint:
        for img in existing_images:
            if img.get("fingerprint") == fingerprint:
                image_match = img
                break

    # Search by name alias via API
    if not image_match:
        fp = _find_image_by_alias(name)
        if fp:
            for img in existing_images:
                if img.get("fingerprint") == fp:
                    image_match = img
                    break

    # Search by additional aliases
    if not image_match and aliases:
        for search_alias in aliases:
            fp = _find_image_by_alias(search_alias)
            if fp:
                for img in existing_images:
                    if img.get("fingerprint") == fp:
                        image_match = img
                        break
                if image_match:
                    break

    # Search by source.alias if provided
    if not image_match and isinstance(source, dict) and source.get("alias"):
        fp = _find_image_by_alias(source["alias"])
        if fp:
            for img in existing_images:
                if img.get("fingerprint") == fp:
                    image_match = img
                    break

    # ========================================================
    # 3. Image is absent → import
    # ========================================================
    if not image_match:
        if not source:
            ret["result"] = False
            ret["comment"] = "Image not found and no source specified for import"
            return ret

        if __opts__.get("test"):
            ret["result"] = None
            ret["changes"]["image"] = {"old": None, "new": source}
            ret["changes"]["aliases"] = {"old": None, "new": desired_aliases}
            ret["comment"] = "Image would be imported"
            return ret

        # Remote import
        if isinstance(source, dict) and source.get("server"):
            imp = __salt__["incus.image_create_from_remote"](
                source["server"],
                alias=source.get("alias"),
                protocol=source.get("protocol", "simplestreams"),
                auto_update=auto_update if auto_update is not None else False,
                public=public if public is not None else False,
                aliases=desired_aliases,
                properties=properties,
            )

            if not imp.get("success"):
                ret["result"] = False
                ret["comment"] = f"Failed to import image: {imp.get('error', 'Unknown error')}"
                return ret

            fingerprint = imp.get("fingerprint")

        # Local import from file
        elif isinstance(source, str):
            imp = __salt__["incus.image_create_from_file"](
                source,
                public=public if public is not None else False,
                properties=properties,
                aliases=desired_aliases,
                auto_update=auto_update if auto_update is not None else False,
            )

            if not imp.get("success"):
                ret["result"] = False
                ret["comment"] = f"Failed to import image: {imp.get('error', 'Unknown error')}"
                return ret

            fingerprint = imp.get("fingerprint")

        else:
            ret["result"] = False
            ret["comment"] = (
                "Invalid source for image import (must be dict with 'server' or file path string)"
            )
            return ret

        # Refresh image list
        updated = __salt__["incus.image_list"](recursion=1)
        if not updated.get("success"):
            ret["result"] = False
            ret["comment"] = f"Failed to refresh image list: {updated.get('error')}"
            return ret

        for img in updated.get("images", []):
            if img.get("fingerprint") == fingerprint:
                image_match = img
                break

        ret["changes"]["imported"] = {"old": None, "new": fingerprint}
        ret["changes"]["aliases"] = {"old": None, "new": desired_aliases}
        ret["comment"] = f"Image imported with fingerprint {fingerprint}"
        return ret

    # ========================================================
    # 4. Image exists → compare and update fields
    # ========================================================
    current = image_match
    diff = {}

    # Check public flag
    if public is not None:
        cur = bool(current.get("public"))
        if cur != bool(public):
            diff["public"] = {"old": cur, "new": public}

    # Check auto_update
    if auto_update is not None:
        cur = bool(current.get("auto_update", False))
        if cur != bool(auto_update):
            diff["auto_update"] = {"old": cur, "new": auto_update}

    # Check aliases
    # Get current aliases via API
    all_aliases_result = __salt__["incus.image_alias_list"](recursion=1)
    if all_aliases_result.get("success"):
        all_aliases = all_aliases_result.get("aliases", [])
        # Filter only aliases for current image
        current_aliases = []
        for alias_obj in all_aliases:
            if isinstance(alias_obj, dict):
                if alias_obj.get("target") == current.get("fingerprint"):
                    alias_name = alias_obj.get("name")
                    if alias_name:
                        current_aliases.append(alias_name)
    else:
        current_aliases = []

    cur_sorted = sorted(current_aliases)
    new_sorted = sorted(desired_aliases)

    if cur_sorted != new_sorted:
        diff["aliases"] = {"old": cur_sorted, "new": new_sorted}

    # Check properties
    if properties is not None:
        cur = current.get("properties", {})
        if cur != properties:
            diff["properties"] = {"old": cur, "new": properties}

    # Check expires_at
    if expires_at is not None:
        cur = current.get("expires_at")
        if cur != expires_at:
            diff["expires_at"] = {"old": cur, "new": expires_at}

    # Check compression_algorithm
    if compression_algorithm is not None:
        cur = current.get("compression_algorithm")
        if cur != compression_algorithm:
            diff["compression_algorithm"] = {"old": cur, "new": compression_algorithm}

    # ========================================================
    # 5. Apply updates if needed
    # ========================================================
    if not diff:
        ret["comment"] = f"Image already present with alias {name} and up-to-date"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["changes"] = diff
        ret["comment"] = "Image would be updated"
        return ret

    # Apply updates
    update_body = {k: v["new"] for k, v in diff.items()}

    upd = __salt__["incus.image_update"](current["fingerprint"], update_body)
    if not upd.get("success"):
        ret["result"] = False
        ret["comment"] = f"Failed to update image: {upd.get('error', 'Unknown error')}"
        return ret

    ret["changes"] = diff
    ret["comment"] = f"Image updated with alias {name}"

    return ret


@log_state_changes
def image_absent(fingerprint=None, alias=None):
    """
    Ensure an image is absent locally.

    :param fingerprint: Optional fingerprint
    :param alias: Optional alias (search via API)

    Example:

    .. code-block:: yaml

        remove_old_image:
          incus.image_absent:
            - alias: old-template
    """
    ret = {
        "name": alias or fingerprint or "image",
        "result": True,
        "changes": {},
        "comment": "",
    }

    fp = None

    # Search by alias via API
    if alias:
        fp = _find_image_by_alias(alias)

    # Search by fingerprint
    if not fp and fingerprint:
        fp = fingerprint

    if not fp:
        ret["comment"] = "Image already absent"
        return ret

    # Check that image exists
    image_info = __salt__["incus.image_get"](fp)
    if not image_info.get("success"):
        ret["comment"] = "Image already absent"
        return ret

    if __opts__.get("test"):
        ret["result"] = None
        ret["changes"] = {"old": fp, "new": None}
        ret["comment"] = "Image would be removed"
        return ret

    delete = __salt__["incus.image_delete"](fp)

    if delete.get("success"):
        ret["comment"] = "Image removed"
        ret["changes"] = {"old": fp, "new": None}
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to delete image: {delete.get('error')}"

    return ret


@log_state_changes
def image_installed(
    name,
    fingerprint=None,
    source=None,
    auto_update=False,
    public=False,
    aliases=None,
    properties=None,
):
    """
    Ensure a single Incus image is imported and configured.

    This is a thin-wrapper over image_present, which allows convenient
    iteration over pillars. The state name becomes the primary alias.

    .. code-block:: yaml

        {% for img_name, img in pillar.get('incus_images', {}).items() %}
        {{ img_name }}:
          incus.image_installed:
            - fingerprint: {{ img.get('fingerprint') }}
            - source: {{ img.get('source') }}
            - auto_update: {{ img.get('auto_update', False) }}
            - public: {{ img.get('public', False) }}
            - aliases: {{ img.get('aliases', []) }}
        {% endfor %}
    """
    return image_present(
        name=name,
        fingerprint=fingerprint,
        source=source,
        auto_update=auto_update,
        public=public,
        aliases=aliases,
        properties=properties,
    )
