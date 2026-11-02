# Camera access from another family computer

## Simple Windows option — no certificate setup

The lesson's photo dialog offers **Open Windows Camera** on Windows network
computers where the embedded preview is unavailable. This launches the Camera
app on the computer using the browser through its registered
`microsoft.windows.camera:` protocol. Approve the browser's Open Camera prompt
if shown, take the photo, return to the lesson and choose the saved image from
Pictures → Camera Roll (which may be in OneDrive). If the protocol handler is
not installed, open Camera from the Start menu.

The browser cannot silently read Camera Roll or choose its newest file. The
person selects the image, reviews it and confirms **Use this photo**. This flow
works without installing a certificate on each Windows device. The live browser
preview remains available on localhost/trusted HTTPS. Secure-connection setup
in Settings is now an optional, collapsed section for families who prefer that.

Registry reference: https://www.iana.org/assignments/uri-schemes/prov/microsoft.windows.camera.

## Optional embedded browser preview

Browsers allow webcam previews on a trusted HTTPS page or on localhost.
An ordinary HTTP LAN IP is not a secure context. Localhost refers to the
computer running that browser, so it cannot point another family computer
back to the home server.

On the home computer, open **Settings → Camera access on other devices**
(`/settings#camera-access`) and select **Enable secure camera access**.
The app adds HTTPS on port 8443 in the same process: it shares the existing
records, jobs and lifecycle. HTTP on port 8000 remains available for existing
tabs, desktop tutor bridges and certificate setup. No tunnel, router forwarding
or internet service is used. The existing private-network and same-origin
guards also protect HTTPS, and remote clients retain their actual addresses;
host-only controls remain unavailable from other computers.

On each computer with a webcam:

1. Open the same Settings section through the usual home-network HTTP address.
2. Download the public home certificate. Check its SHA-256 fingerprint against
   the section on the home computer (or a separately provided trusted copy).
   `Get-FileHash` on the downloaded DER `.cer` file returns this same fingerprint.
3. For Windows Chrome/Edge, open the certificate and choose **Install Certificate**,
   **Current User**, then explicitly select **Trusted Root Certification Authorities**.
   The person using the computer must approve this trust decision. No app code
   installs certificates or changes browser security flags. Other browsers and
   operating systems can require their own trust configuration.
4. Restart the browser and open the supplied secure app address, normally
   `https://<home-server-IP>:8443/`. Do not bypass a certificate warning; complete
   the trust installation or resolve the certificate mismatch instead.
5. Reopen the saved lesson, choose **Take photo**, and approve the browser's
   camera request. A live preview stays on that device until **Use this photo**.

The other computer's certificate trust cannot be granted by server code. An
untrusted HTTPS address alone does not solve camera access. A server handshake
check is also not a claim that the remote computer has approved the camera.

Send any unfinished typed answer before moving to the new address. Saved lesson
state is shared on the server, while browser-local drafts/settings belong to
their original origin. The setup link opens a new tab and leaves the lesson tab
available. A saved-photo chooser inside the camera dialog also works on HTTP;
it previews the selected image and uploads only after confirmation.

Private certificate keys are encrypted in the ignored local `data/https/`
folder; their passwords use the host's DPAPI-backed secret store. Only the
public root certificate has a download route. The public root is stable across
server restarts and LAN IP changes. Leaf certificates are renewed when near
expiry or when a new LAN address is detected. Preserve the local HTTPS files
and their encrypted passwords together; replacing the root requires approving
trust again on the family devices.

The launcher announces the secure addresses when enabled. On later starts the
main app opens the secure listener automatically; failure leaves HTTP and photo
uploads usable and appears in Settings. If another computer cannot reach 8443,
check the home computer's Windows Firewall rule for its server Python program
on the private home network. Never disable the firewall or expose the port to
the public internet to fix camera access.

References: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia,
https://uvicorn.dev/settings/.
