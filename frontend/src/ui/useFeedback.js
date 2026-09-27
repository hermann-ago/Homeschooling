import { createContext, useContext } from 'react';

/*
  In-app replacements for window.confirm and window.alert (see FeedbackProvider):

    const confirm = useConfirm();
    if (await confirm({ title: 'Delete History?', confirmLabel: 'Delete', danger: true })) …

    const toast = useToast();
    toast('Book linked.');                      // or toast({ message, tone: 'problem' })
*/

export const FeedbackContext = createContext(null);

function useFeedback() {
  const value = useContext(FeedbackContext);
  if (!value) throw new Error('Wrap the app in <FeedbackProvider>');
  return value;
}

export const useConfirm = () => useFeedback().confirm;
export const useToast = () => useFeedback().toast;
