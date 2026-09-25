import { createContext, useContext } from 'react';

export const DeviceContext = createContext(null);
export const useDevice = () => useContext(DeviceContext);
