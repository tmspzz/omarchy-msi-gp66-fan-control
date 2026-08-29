# Omarchy MSI GP66 Fan Control

Beta release — `0.1.0-beta`

An Omarchy bar widget for MSI GP66 Leopard `MS-1542` laptops. The plugin
manifest and `BarWidget.qml` are at the repository root, as required for a
Git-hosted Omarchy plugin.

The plugin uses the kernel `ec_sys` interface with the reviewed G1_3 register
layout. A root-owned system service provides read-only status over a local
Unix socket. Explicit Cooler Boost writes use the fixed root-owned helper and
are validated against the board and allow-listed registers.

## Install

```sh
sudo ./install.sh
omarchy restart shell
```

Remove the installed service, helper, client, and widget with:

```sh
sudo ./install.sh --uninstall
```

For a Git-hosted plugin, install it with `omarchy plugin add`, then enable
`msi.gp66-fan-control` in the bar. The system installer is still
required because the MSI embedded controller is protected by the kernel.

The installer loads `ec_sys` read-only at boot and enables the telemetry
service. It does not install Python packages or GUI dependencies.

## Controls

- Fan icon: status and temperatures in the tooltip
- Left-click: enable Cooler Boost through the privileged service
- Right-click: disable Cooler Boost through the privileged service
- Middle-click: refresh status

This plugin specifically targets the MSI GP66 Leopard `MS-1542` family
(10UH/10UE/10UG). It is not a generic MSI fan controller.

The implementation, including Cooler Boost writes, has been hardware-validated
only on an MSI GP66 Leopard 10UH in the `MS-1542` family. Cooler Boost writes
are hardware-specific and must not be enabled on other models or firmware
versions unless separately validated.
Unsupported boards refuse operation. EC writes can affect hardware; use at
your own risk.
