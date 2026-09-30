import { useCallback, useRef } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Button, Feedback, Screen, ui, useLiveData } from '@/components/marketplace-screen';
import { Text } from 'react-native';
import { socialApi } from '@/services/social-api';

export default function StartConversation() {
  const params = useLocalSearchParams<{ scope: string; scopeId: string; farmerId?: string }>();
  const router = useRouter();
  const leaving = useRef(false);
  const load = useCallback(async () => {
    if (params.scope !== 'listing' && params.scope !== 'order') throw new Error('Open a conversation from a listing or order.');
    return socialApi.start(params.scope, params.scopeId, params.farmerId);
  }, [params.scope, params.scopeId, params.farmerId]);
  const conversation = useLiveData(load);
  // Navigation follows a user-visible action after creation, avoiding redirects during render.
  return <Screen title="Start a conversation">
    <Feedback loading={conversation.loading} error={conversation.error} retry={() => void conversation.refresh()} />
    {conversation.value && <>
      <Text style={ui.text}>Your conversation is ready.</Text>
      <Button title="Open conversation" onPress={() => { if (leaving.current) return; leaving.current = true; router.replace({ pathname: '/messages/[conversationId]', params: { conversationId: conversation.value!.id } }); }} />
    </>}
  </Screen>;
}
