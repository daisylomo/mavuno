import { liveRequest } from './live-api.ts';
import { createSocialApi } from './social-contracts.ts';

export const socialApi = createSocialApi(liveRequest);
