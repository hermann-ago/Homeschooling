import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { systemApi } from '../api/system';
import { useDevice } from './deviceContext';
import { modeHref } from '../api/mode';
import { Button } from '../ui';

export default function CameraConnectionSettings() {
  const device = useDevice();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const { data, error, refetch } = useQuery({ queryKey: ['camera-connection'], queryFn: systemApi.cameraConnection, retry: false });
  const enable = async () => {
    setBusy(true); setProblem('');
    try { client.setQueryData(['camera-connection'], await systemApi.enableCameraConnection()); }
    catch (error) { setProblem(error.message); }
    finally { setBusy(false); }
  };
  return <section id="camera-access" className="scroll-mt-6 bg-surface border border-line rounded-2xl p-5 md:p-6 flex flex-col gap-4">
    <h2 className="font-display text-2xl font-medium">Camera &amp; photos</h2>
    <p className="text-sm">On a Windows network computer, choose <strong>Open Windows Camera</strong> in the lesson, take your photo, then choose the saved photo. No certificate setup is needed for this option.</p>
    <details className="rounded-xl border border-line p-3 flex flex-col gap-3">
      <summary className="cursor-pointer font-semibold">Optional: live camera preview inside the browser</summary>
    <p className="text-sm text-muted mt-3">For an embedded webcam preview, browsers need a trusted HTTPS connection. Each device needs this setup; localhost only refers to the computer you are using.</p>
    {error && <><p role="alert">{error.message}</p><Button onClick={() => refetch()}>Retry camera setup</Button></>}
    {data && !data.running && <>
      <p className="text-sm">{data.error || 'The secure home connection is not running yet.'}</p>
      {device?.host && !device?.test_mode ? <Button disabled={busy} onClick={enable}>{busy ? 'Preparing secure connection…' : 'Enable secure camera access'}</Button>
        : <p className="text-sm text-muted">Open this section on the home computer to enable secure camera access.</p>}
    </>}
    {data?.running && <>
      <p className="text-sm text-action">Secure home connection is ready. Complete the trust setup on the computer with the webcam before opening it.</p>
      <ol className="list-decimal pl-5 flex flex-col gap-3 text-sm">
        <li><a className="text-action underline" href={modeHref(data.certificate_download)} download>Download the home certificate</a> on the computer with the webcam. This download contains the public certificate only.</li>
        <li>For Windows with Chrome or Edge: open the certificate, choose <strong>Install Certificate → Current User → Place all certificates in the following store → Browse → Trusted Root Certification Authorities → Finish</strong>. Only install your family server’s certificate after checking its fingerprint below.</li>
        <li>Restart the browser, open the secure app address below and allow camera access when asked. Saved lessons are shared with the usual app.</li>
      </ol>
      <details className="rounded-xl border border-line p-3 text-sm">
        <summary className="cursor-pointer font-semibold">Check the certificate before trusting it</summary>
        <p className="mt-2">Name: Homeschooling home network. Compare this SHA-256 fingerprint with the same section on the home computer. In PowerShell, Get-FileHash on the downloaded .cer file shows its SHA-256 fingerprint.</p>
        <code className="block mt-2 break-all text-xs">{data.certificate_sha256}</code>
        <p className="mt-2 text-xs text-muted">Trusting this certificate authorizes this home server’s local certificate authority on your device. It is not installed automatically.</p>
      </details>
      <a className="text-sm text-action underline break-all" href={data.secure_url} target="_blank" rel="noreferrer">Open secure app: {data.secure_url}</a>
      <p className="text-xs text-muted">The secure app opens in another tab. Send unfinished typed answers before changing addresses. Do not bypass a browser certificate warning; finish the trust setup first. Firefox, macOS and other systems may need their own certificate trust settings.</p>
    </>}
    {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    </details>
  </section>;
}
