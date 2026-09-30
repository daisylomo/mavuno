import { liveRequest } from './live-api';
import { createSocialApi } from './social-contracts';

export const socialApi = createSocialApi(liveRequest);
