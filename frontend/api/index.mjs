import { createGateway } from '../lib/gateway.mjs';

const gateway = createGateway(process.env);

export default { fetch: gateway };
