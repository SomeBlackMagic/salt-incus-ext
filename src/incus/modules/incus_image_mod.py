"""Image management functions for the Incus Salt module."""

import logging
from urllib.parse import quote

__virtualname__ = "incus"


def __virtual__():
    from incus.modules import incus_mod

    return incus_mod.__virtual__()


log = logging.getLogger(__name__)


def _client():
    from incus.modules.incus_mod import IncusClient

    return IncusClient(salt_funcs=__salt__)


# ========== Image Management Functions ==========


def image_list(recursion=0):
    """
    List all images

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_list
        salt '*' incus.image_list recursion=1
    """
    client = _client()
    result = client._request("GET", "/images", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "images": result.get("metadata", [])}


def image_get(fingerprint):
    """
    Get image information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_get <fingerprint>
    """
    client = _client()
    result = client._request("GET", f"/images/{quote(fingerprint)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "image": result.get("metadata", {})}


def image_delete(fingerprint):
    """
    Delete an image

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_delete <fingerprint>
    """
    log.info("Deleting image '%s'", fingerprint)
    client = _client()
    result = client._sync_request("DELETE", f"/images/{quote(fingerprint)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    log.info("Image '%s' deleted", fingerprint)
    return {"success": True, "message": f"Image {fingerprint} deleted successfully"}


def image_create_from_file(
    filename,
    public=False,
    properties=None,
    auto_update=False,  # pylint: disable=unused-argument
    aliases=None,
):
    """
    Upload a local .tar.xz/.tar.gz or qcow2 as an image.

    Incus API:
      POST /1.0/images
        Content-Type: multipart/form-data

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_create_from_file /tmp/rootfs.tar.xz
        salt '*' incus.image_create_from_file /tmp/rootfs.tar.xz public=True aliases="['myimage']"
    """
    log.info("Importing image from '%s'", filename)
    client = _client()
    url = client.base_url + "/images"

    try:
        with open(filename, "rb") as f:
            files = {"file": f}

            headers_data = {
                "X-Incus-public": "1" if public else "0",
            }

            if properties:
                for key, value in properties.items():
                    headers_data[f"X-Incus-properties.{key}"] = str(value)

            response = client.session.post(url, files=files, headers=headers_data, timeout=600)
            response.raise_for_status()
            result = response.json()
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {filename}"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"success": False, "error": str(e)}

    if result.get("type") == "async":
        op_result = client._wait_for_operation(result["operation"])

        # Check for errors
        if op_result.get("error_code") != 0:
            return {"success": False, "error": op_result.get("error", "Unknown error")}

        metadata = op_result.get("metadata", {})
        if isinstance(metadata, dict) and "metadata" in metadata:
            metadata = metadata.get("metadata", {})

        fingerprint = metadata.get("fingerprint")

        # Add aliases if specified
        if aliases and fingerprint:
            for alias_name in aliases:
                alias_data = {"name": alias_name, "target": fingerprint}
                alias_result = client._sync_request("POST", "/images/aliases", data=alias_data)
                if alias_result.get("error_code") != 0:
                    log.warning(f"Failed to add alias {alias_name}: {alias_result.get('error')}")

        return {"success": True, "fingerprint": fingerprint, "metadata": metadata}

    return {"success": True, "metadata": result.get("metadata", {})}


def image_create_from_remote(
    server,
    alias=None,
    protocol="simplestreams",
    image_type=None,
    name=None,
    fingerprint=None,
    project=None,
    auto_update=False,
    public=False,
    aliases=None,
    profiles=None,
    properties=None,
    compression_algorithm=None,
    expires_at=None,
    format=None,
    secret=None,
    certificate=None,
    url=None,
):
    """
    Create an image by pulling from a remote server.

    Fully matches Incus REST API POST /1.0/images.
    Only the ``server`` and one of ``alias`` or ``fingerprint`` are mandatory.
    All other fields are optional and will be included only if specified.
    The result is always an async operation.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_create_from_remote https://images.linuxcontainers.org alias=ubuntu/22.04
        salt '*' incus.image_create_from_remote https://images.linuxcontainers.org alias=ubuntu/22.04 protocol=simplestreams
    """

    # ============
    # VALIDATION
    # ============

    # Mandatory: server
    if not server or not isinstance(server, str):
        return {"success": False, "error": "Parameter 'server' is required and must be a string"}

    # Mandatory: alias XOR fingerprint
    if not alias and not fingerprint:
        return {"success": False, "error": "Either 'alias' or 'fingerprint' must be provided"}

    if alias and fingerprint:
        return {"success": False, "error": "Only one of 'alias' or 'fingerprint' may be provided"}

    # Mandatory protocol
    valid_protocols = ("simplestreams", "incus", "lxd", "direct")
    if protocol not in valid_protocols:
        return {
            "success": False,
            "error": f"Invalid protocol '{protocol}'. Must be one of {valid_protocols}",
        }

    # Optional: type for source (Incus allows "instance", "image")
    if image_type and image_type not in ("container", "virtual-machine", "instance", "image"):
        return {
            "success": False,
            "error": "Invalid image_type. Valid: container, virtual-machine, instance, image",
        }

    # ============
    # BUILD REQUEST
    # ============

    log.info("Importing image from '%s'", server)
    client = _client()

    # Base body
    data = {
        "auto_update": auto_update,
        "public": public,
        "source": {
            "type": "image",
            "mode": "pull",
            "server": server,
            "protocol": protocol,
        },
    }

    # Optional source fields
    if alias:
        data["source"]["alias"] = alias
    if fingerprint:
        data["source"]["fingerprint"] = fingerprint
    if image_type:
        data["source"]["image_type"] = image_type
    if name:
        data["source"]["name"] = name
    if project:
        data["source"]["project"] = project
    if secret:
        data["source"]["secret"] = secret
    if certificate:
        data["source"]["certificate"] = certificate
    if url:
        data["source"]["url"] = url

    # Optional top-level fields
    if properties:
        data["properties"] = properties

    if compression_algorithm:
        data["compression_algorithm"] = compression_algorithm

    if expires_at:
        data["expires_at"] = expires_at

    if format:
        data["format"] = format

    # Perform request
    result = client._sync_request("POST", "/images", data=data)

    # Error always indicated by error_code != 0
    if result.get("error_code") != 0:
        return {
            "success": False,
            "error": result.get("error", "Unknown error"),
        }

    # For async operations (image imports), result.metadata contains the operation
    # and operation.metadata contains the actual result (with fingerprint)
    metadata = result.get("metadata", {})

    # If metadata contains operation metadata, extract it
    if isinstance(metadata, dict) and "metadata" in metadata:
        metadata = metadata.get("metadata", {})

    fingerprint = metadata.get("fingerprint")

    # Add aliases after image is created
    if aliases and fingerprint:
        for alias_name in aliases:
            alias_data = {"name": alias_name, "target": fingerprint}
            alias_result = client._sync_request("POST", "/images/aliases", data=alias_data)
            if alias_result.get("error_code") != 0:
                log.warning(f"Failed to add alias {alias_name}: {alias_result.get('error')}")

    # Add profiles if specified (via image update)
    if profiles and fingerprint:
        update_data = {"profiles": profiles}
        update_result = image_update(fingerprint, update_data)
        if not update_result.get("success"):
            log.warning(f"Failed to set profiles on image: {update_result.get('error')}")

    return {"success": True, "fingerprint": fingerprint, "metadata": metadata}


def image_update_properties(fingerprint, properties):
    """
    Update image properties

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_update_properties <fp> properties="{'os':'ubuntu'}"
    """
    client = _client()

    current = client._request("GET", f"/images/{quote(fingerprint)}")
    if "error" in current:
        return {"success": False, "error": current["error"]}

    data = current.get("metadata", {})
    data["properties"] = data.get("properties", {})
    data["properties"].update(properties)

    result = client._sync_request("PUT", f"/images/{quote(fingerprint)}", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"Image {fingerprint} updated successfully"}


def image_update(fingerprint, update_body):
    """
    Update image metadata (public, auto_update, aliases, properties, etc.)

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_update <fp> update_body="{'public': True, 'auto_update': True}"
        salt '*' incus.image_update <fp> update_body="{'aliases': ['myimage', 'latest']}"

    :param fingerprint: Image fingerprint
    :param update_body: Dictionary with fields to update
    :return: Result dict
    """
    client = _client()

    # Get current image data
    current = client._request("GET", f"/images/{quote(fingerprint)}")
    if current.get("error_code") != 0:
        return {"success": False, "error": current.get("error", "Failed to get image")}

    data = current.get("metadata", {})

    # Handle aliases separately via /images/aliases API
    # Make a copy to avoid modifying the original
    update_body_copy = dict(update_body)
    desired_aliases = update_body_copy.pop("aliases", None)

    # Update other fields
    for key, value in update_body_copy.items():
        data[key] = value

    # Send PUT request for other fields (if any)
    if update_body_copy:
        result = client._sync_request("PUT", f"/images/{quote(fingerprint)}", data=data)

        if result.get("error_code") != 0:
            return {"success": False, "error": result.get("error", "Failed to update image")}

    # Handle aliases separately using /images/aliases API
    if desired_aliases is not None:
        # Get current aliases from the API (not from image metadata)
        all_aliases_result = client._request("GET", "/images/aliases", params={"recursion": 1})
        if all_aliases_result.get("error_code") != 0:
            return {"success": False, "error": "Failed to get current aliases"}

        # Filter aliases for this image
        current_aliases = []
        for alias_obj in all_aliases_result.get("metadata", []):
            if isinstance(alias_obj, dict) and alias_obj.get("target") == fingerprint:
                alias_name = alias_obj.get("name")
                if alias_name:
                    current_aliases.append(alias_name)

        # Determine which aliases to add and remove
        to_add = [a for a in desired_aliases if a not in current_aliases]
        to_remove = [a for a in current_aliases if a not in desired_aliases]

        # Remove old aliases
        for alias_name in to_remove:
            del_result = client._sync_request("DELETE", f"/images/aliases/{quote(alias_name)}")
            if del_result.get("error_code") != 0:
                log.warning(f"Failed to delete alias {alias_name}: {del_result.get('error')}")

        # Add new aliases
        for alias_name in to_add:
            alias_data = {"name": alias_name, "target": fingerprint}
            add_result = client._sync_request("POST", "/images/aliases", data=alias_data)
            if add_result.get("error_code") != 0:
                return {
                    "success": False,
                    "error": f"Failed to add alias {alias_name}: {add_result.get('error')}",
                }

    return {"success": True, "message": f"Image {fingerprint} updated successfully"}


def image_set_public(fingerprint, public=True):
    """
    Set image public or private

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_set_public <fp> public=True
    """
    client = _client()

    current = client._request("GET", f"/images/{quote(fingerprint)}")
    if "error" in current:
        return {"success": False, "error": current["error"]}

    data = current.get("metadata", {})
    data["public"] = public

    result = client._sync_request("PUT", f"/images/{quote(fingerprint)}", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f'Image {fingerprint} set to {"public" if public else "private"}',
    }


def image_alias_list(recursion=0):
    """
    List all image aliases

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_alias_list
        salt '*' incus.image_alias_list recursion=1
    """
    client = _client()
    result = client._request("GET", "/images/aliases", params={"recursion": recursion})

    if result.get("error_code") != 0:
        return {"success": False, "error": result["error"]}

    return {"success": True, "aliases": result.get("metadata", [])}


def image_alias_get(name):
    """
    Get image alias information

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_alias_get ubuntu/22.04
    """
    if not name:
        return {"success": False, "error": "Alias name is required"}

    client = _client()
    result = client._request("GET", f"/images/aliases/{quote(str(name))}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to get alias")}

    return {"success": True, "alias": result.get("metadata", {})}


def image_alias_create(name, target, description=""):
    """
    Create an image alias

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_alias_create myimage <fingerprint>
        salt '*' incus.image_alias_create ubuntu/custom abc123def description="Custom Ubuntu image"
    """
    if not name:
        return {"success": False, "error": "Alias name is required"}
    if not target:
        return {"success": False, "error": "Target fingerprint is required"}

    client = _client()

    data = {"name": name, "target": target}

    if description:
        data["description"] = description

    result = client._sync_request("POST", "/images/aliases", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to create alias")}

    return {"success": True, "message": f"Image alias {name} created successfully"}


def image_alias_update(name, target=None, description=None):
    """
    Update an image alias

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_alias_update myimage target=<new_fingerprint>
        salt '*' incus.image_alias_update myimage description="Updated description"
    """
    if not name:
        return {"success": False, "error": "Alias name is required"}

    client = _client()

    # Get current alias
    current = client._request("GET", f"/images/aliases/{quote(name)}")
    if current.get("error_code") != 0:
        return {"success": False, "error": current.get("error", "Failed to get alias")}

    alias_data = current.get("metadata", {})

    # Update fields
    if target is not None:
        alias_data["target"] = target

    if description is not None:
        alias_data["description"] = description

    result = client._sync_request("PUT", f"/images/aliases/{quote(name)}", data=alias_data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to update alias")}

    return {"success": True, "message": f"Image alias {name} updated successfully"}


def image_alias_rename(name, new_name):
    """
    Rename an image alias

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_alias_rename oldname newname
    """
    if not name or not new_name:
        return {"success": False, "error": "Both old and new alias names are required"}

    client = _client()

    data = {"name": new_name}

    result = client._sync_request("POST", f"/images/aliases/{quote(name)}", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to rename alias")}

    return {"success": True, "message": f"Image alias {name} renamed to {new_name} successfully"}


def image_alias_delete(name):
    """
    Delete an image alias

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_alias_delete ubuntu/22.04
    """
    if not name:
        return {"success": False, "error": "Alias name is required"}

    client = _client()
    result = client._sync_request("DELETE", f"/images/aliases/{quote(name)}")

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to delete alias")}

    return {"success": True, "message": f"Image alias {name} deleted successfully"}


def image_copy(
    fingerprint,
    target_server=None,
    target_certificate=None,
    target_secret=None,
    aliases=None,
    public=False,
    auto_update=False,
):
    """
    Copy an image to another server or within the same server

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_copy <fingerprint> aliases="['myimage-copy']"
        salt '*' incus.image_copy <fingerprint> target_server=https://target:8443 aliases="['remote-copy']"
    """
    if not fingerprint:
        return {"success": False, "error": "Fingerprint is required"}

    client = _client()

    # Get source image
    source_result = client._request("GET", f"/images/{quote(fingerprint)}")
    if source_result.get("error_code") != 0:
        return {"success": False, "error": source_result.get("error", "Failed to get source image")}

    _source_image = source_result.get("metadata", {})

    data = {
        "source": {"type": "copy", "fingerprint": fingerprint},
        "public": public,
        "auto_update": auto_update,
    }

    if target_server:
        data["source"]["server"] = target_server
        data["source"]["mode"] = "pull"
        data["source"]["protocol"] = "incus"

        if target_certificate:
            data["source"]["certificate"] = target_certificate
        if target_secret:
            data["source"]["secret"] = target_secret

    result = client._sync_request("POST", "/images", data=data)

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to copy image")}

    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and "metadata" in metadata:
        metadata = metadata.get("metadata", {})

    new_fingerprint = metadata.get("fingerprint", fingerprint)

    # Add aliases to the new image
    if aliases and new_fingerprint:
        for alias_name in aliases:
            alias_data = {"name": alias_name, "target": new_fingerprint}
            alias_result = client._sync_request("POST", "/images/aliases", data=alias_data)
            if alias_result.get("error_code") != 0:
                log.warning(f"Failed to add alias {alias_name}: {alias_result.get('error')}")

    return {
        "success": True,
        "fingerprint": new_fingerprint,
        "message": f"Image {fingerprint} copied successfully",
    }


def image_export(fingerprint, target_path=None):
    """
    Export an image to a file

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_export <fingerprint> target_path=/tmp/image.tar.gz
    """
    if not fingerprint:
        return {"success": False, "error": "Fingerprint is required"}

    client = _client()
    url = f"{client.base_url}/images/{quote(fingerprint)}/export"

    try:
        response = client.session.get(url, stream=True, timeout=600)
        response.raise_for_status()

        # If target_path not specified, return the content
        if not target_path:
            return {"success": True, "content": response.content}

        # Save to file
        with open(target_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return {"success": True, "message": f"Image {fingerprint} exported to {target_path}"}

    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"success": False, "error": str(e)}


def image_refresh(fingerprint):
    """
    Refresh an image (update from remote source)

    This triggers an update of the image from its original source if auto_update is enabled.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_refresh <fingerprint>
    """
    if not fingerprint:
        return {"success": False, "error": "Fingerprint is required"}

    client = _client()

    # Refresh is done by sending a PATCH request
    result = client._sync_request("PATCH", f"/images/{quote(fingerprint)}", data={})

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to refresh image")}

    return {"success": True, "message": f"Image {fingerprint} refreshed successfully"}


def image_secret_create(fingerprint):
    """
    Create a secret for image access

    This creates a one-time secret that can be used to access a private image
    without authentication. Useful for sharing private images temporarily.

    CLI Example:

    .. code-block:: bash

        salt '*' incus.image_secret_create <fingerprint>
    """
    if not fingerprint:
        return {"success": False, "error": "Fingerprint is required"}

    client = _client()

    result = client._sync_request("POST", f"/images/{quote(fingerprint)}/secret", data={})

    if result.get("error_code") != 0:
        return {"success": False, "error": result.get("error", "Failed to create image secret")}

    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and "metadata" in metadata:
        metadata = metadata.get("metadata", {})

    return {"success": True, "secret": metadata}


__all__ = [
    "image_list",
    "image_get",
    "image_delete",
    "image_create_from_file",
    "image_create_from_remote",
    "image_update_properties",
    "image_update",
    "image_set_public",
    "image_alias_list",
    "image_alias_get",
    "image_alias_create",
    "image_alias_update",
    "image_alias_rename",
    "image_alias_delete",
    "image_copy",
    "image_export",
    "image_refresh",
    "image_secret_create",
]
