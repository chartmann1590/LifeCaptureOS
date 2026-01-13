# Security Policy (SECURITY.md)

LifeCaptureOS is an MVP project focused on personal experimentation and privacy. While we strive for security, it is currently a reference implementation and should be deployed with caution.

## 1. Security Best Practices for Users

To keep your LifeCaptureOS deployment secure, we recommend the following:

- **Private Network**: Host your backend and Ollama instance on a secure home network. Avoid exposing them directly to the public internet without a VPN or reverse proxy with strong authentication.
- **HTTPS**: Configure your backend with SSL/TLS (using tools like Nginx and Let's Encrypt) to encrypt data in transit between the ESP32-CAM, Android App, and Backend.
- **Physical Security**: Your data is stored on an SD card on the device. Ensure the physical device is kept secure.
- **Strong Tokens**: Use long, complex device tokens when provisioning.

## 2. Reporting a Vulnerability

If you discover a security vulnerability, please help us by reporting it.
- **Process**: Please open a GitHub Issue with the prefix `[SECURITY]` or contact the maintainers directly if a private communication channel is provided in the repository.
- **Disclosure**: We appreciate responsible disclosure and will aim to address critical security issues promptly.

## 3. Known Limitations (MVP Status)

- **Unencrypted SD Card**: Data on the microSD card is currently stored in plain JPG/JSON format.
- **HTTP by Default**: The current MVP examples may use HTTP for simplicity in local setups. Upgrade to HTTPS for any production-like use.
- **BLE Pairing**: Standard BLE security is used; stay aware of your surroundings when pairing new devices.

## 4. Updates

We periodically update the firmware, backend, and app. Check the repository regularly for security-related patches.

---
*Thank you for helping keep LifeCaptureOS secure.*
