# Contributing

## Module naming convention

All execution and state modules under the `incus` namespace share
`__virtualname__ = "incus"`. Salt merges them at load time. The exception is
`incus_pki_mod`, which requires the `cryptography` package and therefore lives
in its own `incus_pki` namespace.

Functions within a shared virtual namespace must have unique exported names.
Use `__func_alias__` only when a Python function name cannot match the desired
Salt function name, for example when the desired name is a Python keyword.
