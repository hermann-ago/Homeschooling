/* @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import CameraConnectionSettings from './CameraConnectionSettings';
import { DeviceContext } from './deviceContext';
const api=vi.hoisted(()=>({cameraConnection:vi.fn(),enableCameraConnection:vi.fn()}));
vi.mock('../api/system',()=>({systemApi:api}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function show(host=false) {
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>
    <DeviceContext.Provider value={{host}}><CameraConnectionSettings/></DeviceContext.Provider></QueryClientProvider>);
}
it('offers the public certificate and secure address on a remote computer without installing trust automatically', async()=>{
  api.cameraConnection.mockResolvedValue({running:true,certificate_download:'/api/network/camera/certificate',
    secure_url:'https://192.168.1.5:8443/',certificate_sha256:'SYNTHETIC-FINGERPRINT'});
  show();
  expect(screen.getByText(/No certificate setup is needed for this option/)).toBeTruthy();
  const { fireEvent } = await import('@testing-library/react');
  fireEvent.click(screen.getByText('Optional: live camera preview inside the browser'));
  expect(await screen.findByRole('link',{name:'Download the home certificate'})).toBeTruthy();
  expect(screen.getByRole('link',{name:/Open secure app:/}).getAttribute('href')).toBe('https://192.168.1.5:8443/');
  expect(screen.getByText(/Current User/)).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Enable secure camera access'})).toBeNull();
  expect(api.enableCameraConnection).not.toHaveBeenCalled();
});
it('does not offer an unavailable HTTPS address and directs a remote device to host setup',async()=>{
  api.cameraConnection.mockResolvedValue({running:false,enabled:false}); show();
  expect(await screen.findByText(/Open this section on the home computer/)).toBeTruthy();
  expect(screen.queryByRole('link',{name:/Open secure app:/})).toBeNull();
});
