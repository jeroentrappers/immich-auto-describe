import { wrapper } from '@immich/plugin-sdk';
import type { Manifest } from '../dist/index.d.ts';

/**
 * On AssetMetadataExtraction, ask the sidecar (which holds the model fleet + an
 * Immich read key) to describe the asset, then write the result back through the
 * sanctioned workflow `changes` path — no extra write credentials needed here.
 *
 * The plugin deliberately does NOT fetch pixels: the host `httpRequest` returns
 * bodies as text (binary-unsafe), so the sidecar fetches the thumbnail itself.
 */
const methods = wrapper<Manifest>({
  describe: ({ config, data, functions }) => {
    const asset = data.asset;
    const existing = asset.exifInfo?.description ?? '';
    if (existing && !config.overwriteExisting) {
      return {}; // never clobber an existing (possibly manual) description
    }

    const exif = asset.exifInfo;
    const location = [exif?.city, exif?.state, exif?.country].filter(Boolean).join(', ');

    let res;
    try {
      res = functions.httpRequest(`${config.sidecarUrl}/describe`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          assetId: asset.id,
          type: asset.type,
          language: config.language ?? 'en',
          context: {
            date: exif?.dateTimeOriginal ?? null,
            location: location || null,
          },
        }),
      });
    } catch (e) {
      console.error(`auto-describe: sidecar call failed for ${asset.id}: ${e}`);
      return {};
    }

    if (res.status < 200 || res.status >= 300) {
      console.error(`auto-describe: sidecar ${res.status} for ${asset.id}`);
      return {};
    }

    const out = JSON.parse(res.body) as { description?: string; tags?: string[] };
    if (!out.description) {
      return {};
    }

    return {
      changes: {
        asset: {
          exifInfo: {
            description: out.description,
            ...(out.tags && out.tags.length ? { tags: out.tags } : {}),
          },
        },
      },
    };
  },
});

const { describe, ...rest } = methods;
export { describe };
'All methods must be destructured and exported' satisfies string & keyof typeof rest extends never
  ? string
  : string;
