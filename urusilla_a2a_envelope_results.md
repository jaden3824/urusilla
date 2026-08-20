# Full A2A v1 JSON request-envelope benchmark

Corpus: `urusilla-benchmark-corpus-v1`, 280 deterministic messages, SHA-256 `61eb38e3a52d2060e77d43c94ec5d1bd6febf3183d8ecd70ff26724bb28fcddc`  
A2A reference: latest released v1.0 request shapes (`A2A-Version: 1.0`), using the [A2A v1.0.0 specification](https://a2a-protocol.org/v1.0.0/specification/)  
Deterministic full-request suite SHA-256: `9dacc039943c890bc857418e694b0169a61ca9d259ab6f9eb33e9aaa61b49df0`  
Fixed unsigned test `source_id`: `defc2efc4f0ac1ecd553fb45df7abe93`

## Result and scope

The tables below are byte accounting for complete representative HTTP/1.1 requests. They include the request line, `Host`, `A2A-Version`, `A2A-Extensions`, `Content-Type`, `Content-Length`, and the JSON body. The gzip rows compress each JSON body independently with Python gzip level 6, `mtime=0`, an empty filename, and the canonical unknown-OS header byte; their full-request totals also include `Content-Encoding: gzip`, while HTTP headers remain uncompressed.

The measurement does not establish that one representation is faster, better understood by models, safer, or more effective at completing tasks. It is a fixed synthetic, already-structured, in-domain corpus. The v0.2 profile was manually specialized for this schema family and its wrapper is explicitly experimental.

## Measured bytes

| Representation | Binding | JSON body raw total | Full request raw total | JSON body gzip total | Full request gzip total | Full raw p50/msg | Full gzip p50/msg |
|---|---|---:|---:|---:|---:|---:|---:|
| Structured UrusillaIR DataPart baseline | HTTP+JSON SendMessageRequest | 343,684 | 394,016 | 202,899 | 259,739 | 1,285 | 890 |
| Structured UrusillaIR DataPart baseline | JSON-RPC SendMessage | 360,096 | 406,816 | 212,218 | 265,418 | 1,331 | 910 |
| UrusillaWire v0.1 Base64 RawPart | HTTP+JSON SendMessageRequest | 314,076 | 364,351 | 235,679 | 292,596 | 1,210 | 991 |
| UrusillaWire v0.1 Base64 RawPart | JSON-RPC SendMessage | 330,488 | 377,164 | 245,591 | 298,878 | 1,256 | 1,013 |
| UrusillaWire v0.2 warm Base64 RawPart | HTTP+JSON SendMessageRequest | 207,776 | 263,216 | 149,202 | 211,362 | 946 | 756 |
| UrusillaWire v0.2 warm Base64 RawPart | JSON-RPC SendMessage | 224,188 | 275,988 | 158,641 | 217,161 | 991 | 776 |

Every total covers exactly `280` independent requests. Base64 expansion, A2A Message fields, extension declarations, extension metadata, the JSON-RPC request object, and the binding-specific HTTP headers are included where applicable. JSON uses sorted keys and minified UTF-8 solely to make the harness deterministic; A2A does not require this member order.

The structured row carries canonical UrusillaIR in a standard `data` Part and retains the same current extension/source-pin footprint for comparison. It is not a newly implemented path in the hardened adapter. The v0.1 row calls the current `wrap_a2a_message` and `unwrap_a2a_message` paths. The v0.2 row uses a distinct benchmark-only extension URI, media type parameter, and metadata marker, and is not accepted by the v0.1 adapter.

## Exact and deterministic round-trip

| Representation | Binding | Raw exact | gzip exact | Raw byte-deterministic | gzip byte-deterministic |
|---|---|---:|---:|---:|---:|
| Structured UrusillaIR DataPart baseline | HTTP+JSON SendMessageRequest | 280/280 | 280/280 | 280/280 | 280/280 |
| Structured UrusillaIR DataPart baseline | JSON-RPC SendMessage | 280/280 | 280/280 | 280/280 | 280/280 |
| UrusillaWire v0.1 Base64 RawPart | HTTP+JSON SendMessageRequest | 280/280 | 280/280 | 280/280 | 280/280 |
| UrusillaWire v0.1 Base64 RawPart | JSON-RPC SendMessage | 280/280 | 280/280 | 280/280 | 280/280 |
| UrusillaWire v0.2 warm Base64 RawPart | HTTP+JSON SendMessageRequest | 280/280 | 280/280 | 280/280 | 280/280 |
| UrusillaWire v0.2 warm Base64 RawPart | JSON-RPC SendMessage | 280/280 | 280/280 | 280/280 | 280/280 |

`Exact` means the harness parsed the complete HTTP request, checked the service and content headers, decompressed when applicable, validated the selected binding body, decoded its Part, and recovered the exact canonical source message. `Byte-deterministic` means an independent rebuild produced the same complete request bytes. This is deterministic serialization within these pinned profiles, not a claim that all conforming A2A implementations emit identical JSON bytes.

## Aggregate request digests

Each digest covers an ordered sequence of complete requests with an eight-byte big-endian length prefix before every request.

| Representation | Binding | Raw request stream SHA-256 | gzip request stream SHA-256 |
|---|---|---|---|
| Structured UrusillaIR DataPart baseline | HTTP+JSON SendMessageRequest | `8ff512c5052122c9309fa9c713d04630057b3c268785b1afb295656023dbb174` | `7bb05fb5b0c65116f8518f734930788c9e2a4338b3ed1da0463645593030053f` |
| Structured UrusillaIR DataPart baseline | JSON-RPC SendMessage | `78dc6a2ca61e93cd2ba943b5c3a357f79e9136332db3c4c4c6394cf8ecbb7906` | `5b988dd93ca3b4de7c3e15b669ef59f937fd5121fdb6a14e059ac289a39b23db` |
| UrusillaWire v0.1 Base64 RawPart | HTTP+JSON SendMessageRequest | `bb54cef16193b3f71c4e7b67483afcfc724c291117236fd2eb8051cf134e9686` | `a62c84f308ef50f8a723acbde71b4793cab10d6213360f776fc6388a32942b14` |
| UrusillaWire v0.1 Base64 RawPart | JSON-RPC SendMessage | `8ccaea003cf03fd647174cc6e1e4b91eae35643b03eee74011211a9cf5c810fc` | `022c5bb273c92008380768b4d1d10bca44407c1acee4768101b95b4af3bf5f4e` |
| UrusillaWire v0.2 warm Base64 RawPart | HTTP+JSON SendMessageRequest | `3bbaeed21efbf6abcc61194ed8985c5f132f7845a58ce28b0ed5e9013934de12` | `6fff1b7dbfa1f869eaaaabed25923f6df2e20b9f2fe03ace3d31c7b27b438030` |
| UrusillaWire v0.2 warm Base64 RawPart | JSON-RPC SendMessage | `062f7179c4d4c0912bee93e8197a8764130f0036786bec5e5dfbcd5aafa08d6b` | `5dbfe69554055e3d5cfb903afb66fde91e7e412bef4da582593f318085066653` |

## Representative HTTP/1.1 request headers

The following heads are from corpus message 1 using the current v0.1 RawPart. `Content-Length` is the exact byte length of that request body after any indicated content coding. The JSON-RPC path is representative; an actual endpoint is selected from the peer's Agent Card.

HTTP+JSON, raw body:

```http
POST /message:send HTTP/1.1
Host: agent.example.test
A2A-Version: 1.0
A2A-Extensions: urn:urusilla:experimental:0.1
Content-Type: application/a2a+json
Content-Length: 926
```

JSON-RPC, raw body:

```http
POST /rpc HTTP/1.1
Host: agent.example.test
A2A-Version: 1.0
A2A-Extensions: urn:urusilla:experimental:0.1
Content-Type: application/json
Content-Length: 983
```

HTTP+JSON, per-message gzip body:

```http
POST /message:send HTTP/1.1
Host: agent.example.test
A2A-Version: 1.0
A2A-Extensions: urn:urusilla:experimental:0.1
Content-Type: application/a2a+json
Content-Encoding: gzip
Content-Length: 713
```

The structured and v0.1 rows activate `urn:urusilla:experimental:0.1`. The v0.2 experimental row activates `urn:urusilla:experimental:0.2-envelope-benchmark`.

## Cold v0.2 profile cost

The warm v0.2 row depends on the default static profile with `109` strings, `19` map shapes, and dictionary ID `7d12fc414eae60b2`. Its serialized profile capsule is reported separately and is not added to any warm-request total.

| Object | Raw bytes | Per-object gzip bytes | SHA-256 of raw object |
|---|---:|---:|---|
| Experimental v0.2 static-profile capsule | 1,402 | 920 | `b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6` |

This profile-only cold number excludes Agent Card discovery, profile authorization, cache validation, negotiation round trips, the existing Grammar Capsule, source manifest delivery, and fallback setup. A deployment must model those costs before claiming a session break-even.

## Fixed unsigned source-manifest fixture and security boundary

All rows use `defc2efc4f0ac1ecd553fb45df7abe93`, derived from a fixed unsigned source-manifest fixture, so the hot-message metadata footprint and derivation are explicit. Every artifact location in the fixture is an immutable-shaped GitHub URL, but the commit values and conformance digest are synthetic test vectors, the URLs are not fetched, and the manifest is not signature-verified. It must not be used as production provenance. It does not authenticate the semantic sender. The benchmark supplies the known sender to local decode checks, but sends no credential and performs no authentication protocol.

UrusillaWire checksums and gzip CRCs detect accidental damage; they are not signatures, authorization, replay protection, or integrity against an attacker who can recompute them. No request in this research artifact authorizes an external side effect.

## Strict limitations

- The corpus is synthetic and already contains valid UrusillaIR. Natural-language translation, ambiguity, omissions, repair turns, model input/output tokens, task success, and receiver comprehension are not measured.
- The v0.2 dictionary and shapes were manually derived from this benchmark family. The v0.2 numbers are an in-domain warm-profile result, not an out-of-domain or general compression claim.
- HTTP+JSON counts the required `SendMessageRequest.message` field. JSON-RPC counts `jsonrpc`, a deterministic one-based numeric `id`, `method: SendMessage`, and the same request under `params`. Optional `tenant`, `configuration`, and request-level `metadata` are omitted.
- The representative HTTP/1.1 head omits `Authorization`, `Accept`, `User-Agent`, cookies, tracing, proxies, and deployment-specific headers. Request-body gzip support must be negotiated or known; this benchmark does not show that every A2A server accepts `Content-Encoding: gzip`.
- TLS records, TCP/IP packets, DNS, connection setup, retransmission, HTTP/2 or HTTP/3 framing, responses, streaming, gRPC, persistence, and storage are excluded. The totals therefore are not end-to-end network cost.
- Gzip is independent per message with no shared stream or dictionary. Other compression levels, zstd, CBOR, schema-equivalent Protobuf, and production SDK serialization could change the ordering.
- This is not an A2A conformance suite, a deployed client/server measurement, or evidence of official registration or standardization of any private extension URI or media type.

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 urusilla_a2a_envelope_benchmark.py
PYTHONDONTWRITEBYTECODE=1 python3 test_urusilla_a2a_envelope_benchmark.py
```

The report has no timestamp or machine-dependent timing field, so the same source files, canonical gzip helper, Python JSON behavior, corpus version, and default options produce the same report bytes. Corpus and request-stream digests fail visibly if serialization changes.
