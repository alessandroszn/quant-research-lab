# Security

Quant Research Lab runs locally. The library, the command line and the desktop app make no
network calls except the explicit data downloads (`qrlab.data.download*`). They store no
credentials.

## Reporting a problem

Please report a vulnerability privately through GitHub: on the repository's **Security** tab,
choose **Report a vulnerability**. Do not open a public issue for it.

Two kinds of problem count as security problems here:

- personal data, such as portfolio files, leaking into outputs, logs or published files;
- a downloaded or bundled file that could run code.

Fixes are released as patch versions and listed in the CHANGELOG.
