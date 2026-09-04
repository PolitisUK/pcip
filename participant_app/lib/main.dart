// The original MVP is deliberately compact; keep its existing style without
// allowing the style-only lint to obscure correctness diagnostics.
// ignore_for_file: curly_braces_in_flow_control_structures, use_null_aware_elements

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:image_picker/image_picker.dart';
import 'package:file_picker/file_picker.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
import 'package:geolocator/geolocator.dart';

import 'legal_content.dart';
import 'legal_privacy.dart';

abstract class ParticipantApi {
  Future<Map<String, dynamic>> exchange(String invitation);
  Future<Map<String, dynamic>> session();
  Future<List<Map<String, dynamic>>> availableStudies();
  Future<Map<String, dynamic>> switchStudy(int studyId);
  Future<Map<String, dynamic>> legalDocuments();
  Future<void> consent(Map<String, String> documentHashes);
  Future<void> logout();
}

class ApiError implements Exception {
  const ApiError(
    this.message, {
    this.retryable = true,
    this.category,
    this.statusCode,
  });
  final String message;
  final bool retryable;
  final String? category;
  final int? statusCode;
}

const _allowLocalQaHttp = bool.fromEnvironment('PCIP_LOCAL_QA');
// Matches the deployed PCIP BASE_URL in .github/workflows/deploy-azure.yml.
const _configuredReleaseApiBase = String.fromEnvironment(
  'PCIP_API_BASE_URL',
  defaultValue: 'https://citizencentric.co.uk',
);
const _configuredDebugApiBase = String.fromEnvironment('PCIP_QA_API_BASE_URL');
bool _isQaHttpBase(Uri base) =>
    kDebugMode &&
    _allowLocalQaHttp &&
    base.scheme == 'http' &&
    (base.host == 'localhost' || base.host == '10.0.2.2');
String selectedApiBaseValue({
  required bool debugMode,
  required String releaseValue,
  required String debugValue,
}) => debugMode && debugValue.isNotEmpty ? debugValue : releaseValue;
Uri? configuredApiBase() {
  final configured = selectedApiBaseValue(
    debugMode: kDebugMode,
    releaseValue: _configuredReleaseApiBase,
    debugValue: _configuredDebugApiBase,
  );
  final base = Uri.tryParse(configured);
  if (base == null || base.host.isEmpty) return null;
  if (base.scheme != 'https' && !_isQaHttpBase(base)) return null;
  return base.replace(path: base.path.replaceFirst(RegExp(r'/+$'), ''));
}

bool allowsApiBase(Uri base) {
  final configured = configuredApiBase();
  return configured != null &&
      base.scheme == configured.scheme &&
      base.host == configured.host &&
      base.port == configured.port &&
      base.path.replaceFirst(RegExp(r'/+$'), '') ==
          configured.path.replaceFirst(RegExp(r'/+$'), '');
}

String? invitationCodeError(String value) =>
    value.trim().isEmpty ? 'Enter your one-time app code to continue.' : null;
bool invitationRequiresConsent(Map<String, dynamic>? session) {
  final action = session?['next_action'];
  if (action is String) return action == 'consent_required';
  final invitation = session?['invitation'];
  return invitation is Map && invitation['accepted_at'] == null;
}

bool invitationRequiresStudyDocuments(Map<String, dynamic>? session) {
  final invitation = session?['invitation'];
  return invitation is Map && invitation['requires_study_documents'] == true;
}

String participantDateTime(Object? value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '');
  if (parsed == null) return 'Date unavailable';
  final local = parsed.toLocal();
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(local.day)}/${two(local.month)}/${local.year} at ${two(local.hour)}:${two(local.minute)}';
}

String mediaContentType(String filename, String kind) {
  final extension = filename.toLowerCase().split('.').last;
  const byExtension = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'webp': 'image/webp',
    'heic': 'image/heic',
    'm4a': 'audio/mp4',
    'mp3': 'audio/mpeg',
    'wav': 'audio/wav',
    'mp4': 'video/mp4',
    'mov': 'video/quicktime',
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'txt': 'text/plain',
  };
  return byExtension[extension] ??
      (kind == 'photo'
          ? 'image/jpeg'
          : kind == 'voice'
          ? 'audio/mp4'
          : kind == 'video'
          ? 'video/mp4'
          : 'application/octet-stream');
}

class Api implements ParticipantApi {
  Api(this.base, this.token, {http.Client? client})
    : _client = client ?? http.Client();
  final Uri base;
  final String? token;
  final http.Client _client;
  Future<Map<String, dynamic>> request(
    String method,
    String path, {
    Object? body,
    String? idempotencyKey,
  }) async {
    if (!allowsApiBase(base))
      throw const ApiError('A secure service connection is unavailable.');
    final r = http.Request(method, base.resolve(path))
      ..headers.addAll({
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (token case final value?) 'Authorization': 'Bearer $value',
        if (idempotencyKey case final key?) 'Idempotency-Key': key,
      })
      ..body = body == null ? '' : jsonEncode(body);
    late http.Response x;
    try {
      x = await http.Response.fromStream(await _client.send(r));
    } on SocketException {
      throw ApiError(
        'A network connection is unavailable.',
        category: 'network',
      );
    } on TimeoutException {
      throw const ApiError(
        'The service connection timed out.',
        category: 'timeout',
      );
    } on http.ClientException {
      throw const ApiError(
        'A network connection is unavailable.',
        category: 'network',
      );
    }
    if (x.statusCode == 401) {
      throw const ApiError(
        'Your session has ended.',
        retryable: false,
        category: 'session_ended',
        statusCode: 401,
      );
    }
    if (x.statusCode == 400 && path == '/api/v1/participant/session/exchange')
      throw const ApiError(
        'This app code is invalid, expired or already used.',
        retryable: false,
        category: 'invitation_rejected',
        statusCode: 400,
      );
    if (x.statusCode == 429 || x.statusCode >= 500) {
      throw ApiError(
        'The service is temporarily unavailable. Please try again.',
        category: x.statusCode == 429 ? 'rate_limited' : 'server_error',
        statusCode: x.statusCode,
      );
    }
    if (x.statusCode < 200 || x.statusCode > 299) {
      throw ApiError(
        'We could not complete that safely. Please try again.',
        retryable: false,
        category: 'request_rejected',
        statusCode: x.statusCode,
      );
    }
    return Map<String, dynamic>.from(jsonDecode(x.body));
  }

  @override
  Future<Map<String, dynamic>> exchange(String invitation) => request(
    'POST',
    '/api/v1/participant/session/exchange',
    body: {'invitation_token': invitation},
  );
  @override
  Future<Map<String, dynamic>> session() =>
      request('GET', '/api/v1/participant/session');
  @override
  Future<List<Map<String, dynamic>>> availableStudies() async {
    final result = await request(
      'GET',
      '/api/v1/participant/session/available-studies',
    );
    final data = result['data'];
    if (data is! List) return const [];
    return data.map((item) => Map<String, dynamic>.from(item as Map)).toList();
  }

  @override
  Future<Map<String, dynamic>> switchStudy(int studyId) => request(
    'POST',
    '/api/v1/participant/session/switch',
    body: {'study_id': studyId},
  );
  @override
  Future<Map<String, dynamic>> legalDocuments() =>
      request('GET', '/api/v1/participant/legal-documents');
  @override
  Future<void> consent(Map<String, String> documentHashes) async {
    await request(
      'POST',
      '/api/v1/participant/consent',
      body: {'consent': true, 'document_hashes': documentHashes},
    );
  }

  @override
  Future<void> logout() async {
    await request('DELETE', '/api/v1/participant/session');
  }

  Future<List<dynamic>> activities() async =>
      (await request('GET', '/api/v1/participant/activities'))['data']
          as List<dynamic>;
  Future<Map<String, dynamic>> portal() =>
      request('GET', '/api/v1/participant/portal');
  Future<void> draft(
    int id,
    String answer,
    String key, {
    Map<String, dynamic>? location,
  }) => draftResponse(id, key, answer: answer, location: location);

  Future<void> draftResponse(
    int id,
    String key, {
    String? answer,
    List<String> choices = const [],
    Map<String, dynamic>? location,
  }) async {
    await request(
      'PUT',
      '/api/v1/participant/activities/$id/draft',
      body: {
        'answer': answer,
        'choices': choices,
        if (location != null) 'location': location,
      },
      idempotencyKey: key,
    );
  }

  Future<void> submit(
    int id,
    String answer,
    String key, {
    Map<String, dynamic>? location,
  }) => submitResponse(id, key, answer: answer, location: location);

  Future<void> submitResponse(
    int id,
    String key, {
    String? answer,
    List<String> choices = const [],
    Map<String, dynamic>? location,
  }) async {
    await request(
      'POST',
      '/api/v1/participant/activities/$id/submit',
      body: {
        'answer': answer,
        'choices': choices,
        if (location != null) 'location': location,
      },
      idempotencyKey: key,
    );
  }

  Future<Map<String, dynamic>> profile() =>
      request('GET', '/api/v1/participant/profile');
  Future<Map<String, dynamic>> updatePreference(String value, String key) =>
      request(
        'PUT',
        '/api/v1/participant/profile',
        body: {'communication_preference': value},
        idempotencyKey: key,
      );
  Future<List<dynamic>> history() async =>
      (await request('GET', '/api/v1/participant/submissions'))['data']
          as List<dynamic>;
  Future<List<dynamic>> messages() async =>
      (await request('GET', '/api/v1/participant/messages'))['data']
          as List<dynamic>;
  Future<Map<String, dynamic>> sendMessage(String body, String key) => request(
    'POST',
    '/api/v1/participant/messages',
    body: {'body': body},
    idempotencyKey: key,
  );
  Future<Map<String, dynamic>> uploadEvidence(
    int activityId,
    String path,
    String name,
    String contentType,
    String key,
  ) async {
    if (!allowsApiBase(base)) {
      throw const ApiError('A secure service connection is unavailable.');
    }
    final r =
        http.MultipartRequest(
            'POST',
            base.resolve(
              '/api/v1/participant/activities/$activityId/evidence-uploads',
            ),
          )
          ..headers.addAll({
            'Accept': 'application/json',
            if (token case final value?) 'Authorization': 'Bearer $value',
            'Idempotency-Key': key,
          })
          ..fields['activity_id'] = '$activityId'
          ..files.add(
            await http.MultipartFile.fromPath(
              'file',
              path,
              filename: name,
              contentType: MediaType.parse(contentType),
            ),
          );
    final x = await http.Response.fromStream(await r.send());
    if (x.statusCode == 401) throw const ApiError('Your session has ended.');
    if (x.statusCode == 409) {
      throw const ApiError(
        'This activity has already been submitted.',
        retryable: false,
        category: 'already_submitted',
      );
    }
    if (x.statusCode == 400 || x.statusCode == 415) {
      throw const ApiError(
        'This file was rejected by the security checks. Choose a different file.',
        retryable: false,
      );
    }
    if (x.statusCode < 200 || x.statusCode > 299)
      throw const ApiError('We could not upload that file. Please try again.');
    return Map<String, dynamic>.from(jsonDecode(x.body));
  }

  Future<Map<String, dynamic>> uploadPhoto(
    int activityId,
    XFile photo,
    String key,
  ) => uploadEvidence(
    activityId,
    photo.path,
    photo.name,
    mediaContentType(photo.name, 'photo'),
    key,
  );

  Future<Map<String, dynamic>> evidenceStatus(int id) =>
      request('GET', '/api/v1/participant/evidence/$id/status');
  Future<Map<String, dynamic>> uploadDocument(
    int activityId,
    String path,
    String name,
    String key,
  ) => uploadEvidence(
    activityId,
    path,
    name,
    mediaContentType(name, 'document'),
    key,
  );

  Future<Map<String, dynamic>> uploadAudio(
    int activityId,
    String path,
    String key,
  ) => uploadEvidence(activityId, path, 'voice-diary.m4a', 'audio/mp4', key);
  Future<Uint8List> evidenceBytes(int evidenceId) async {
    if (!allowsApiBase(base)) {
      throw const ApiError('A secure service connection is unavailable.');
    }
    final response = await http.get(
      base.resolve('/api/v1/participant/evidence/$evidenceId'),
      headers: {
        'Accept': '*/*',
        if (token case final value?) 'Authorization': 'Bearer $value',
      },
    );
    if (response.statusCode == 401) {
      throw const ApiError('Your session has ended.');
    }
    if (response.statusCode < 200 || response.statusCode > 299) {
      throw const ApiError('That file is not ready to open.');
    }
    return response.bodyBytes;
  }

  Future<Map<String, dynamic>> withdraw(String key) => request(
    'POST',
    '/api/v1/participant/privacy/withdrawal-requests',
    body: {'scope': 'study', 'confirmed': true},
    idempotencyKey: key,
  );
  Future<Map<String, dynamic>> deletion(String key, String scope) => request(
    'POST',
    '/api/v1/participant/privacy/deletion-requests',
    body: {'mode_preference': 'delete', 'scope': scope, 'confirmed': true},
    idempotencyKey: key,
  );
}

Future<void> clearParticipantCache(SharedPreferences prefs) async {
  final pendingMedia = prefs.getStringList('media_upload_queue') ?? const [];
  for (final row in pendingMedia) {
    try {
      final path = (jsonDecode(row) as Map)['local_path'] as String;
      final file = File(path);
      if (await file.exists()) await file.delete();
    } catch (_) {}
  }
  final sensitive = prefs
      .getKeys()
      .where(
        (key) =>
            key.startsWith('cached_profile') ||
            key.startsWith('cached_history') ||
            key.startsWith('cached_messages') ||
            key == 'submission_queue' ||
            key == 'media_upload_queue' ||
            key == 'evidence_receipts' ||
            key.startsWith('draft_'),
      )
      .toList();
  for (final key in sensitive) {
    await prefs.remove(key);
  }
  try {
    final voice = File(
      '${(await getTemporaryDirectory()).path}/voice-diary.m4a',
    );
    if (await voice.exists()) await voice.delete();
  } catch (_) {}
}

Future<Map<String, dynamic>?> cachedObject(String key) async {
  final prefs = await SharedPreferences.getInstance();
  final value = prefs.getString(key);
  if (value == null) return null;
  try {
    final decoded = jsonDecode(value);
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
  } catch (_) {}
  await prefs.remove(key);
  return null;
}

Future<List<dynamic>?> cachedList(String key) async {
  final prefs = await SharedPreferences.getInstance();
  final value = prefs.getString(key);
  if (value == null) return null;
  try {
    final decoded = jsonDecode(value);
    if (decoded is List) return decoded;
  } catch (_) {}
  await prefs.remove(key);
  return null;
}

String studyCacheKey(String base, int? studyId) =>
    studyId == null ? base : '${base}_study_$studyId';

String activityDraftKey(int activityId, int? studyId) => studyId == null
    ? 'draft_$activityId'
    : 'draft_study_${studyId}_activity_$activityId';

Future<String?> readActivityDraft(int activityId, int? studyId) async {
  final preferences = await SharedPreferences.getInstance();
  final scopedKey = activityDraftKey(activityId, studyId);
  final scoped = preferences.getString(scopedKey);
  if (scoped != null || studyId == null) return scoped;
  final legacyKey = activityDraftKey(activityId, null);
  final legacy = preferences.getString(legacyKey);
  if (legacy != null) {
    await preferences.setString(scopedKey, legacy);
    await preferences.remove(legacyKey);
  }
  return legacy;
}

class SessionStore {
  SessionStore(this.storage);
  final FlutterSecureStorage storage;
  Future<void> save(String url, String token) => Future.wait([
    storage.write(key: 'api_url', value: url),
    storage.write(key: 'access_token', value: token),
  ]);
  Future<(String, String)?> read() async {
    final u = await storage.read(key: 'api_url');
    final t = await storage.read(key: 'access_token');
    return u == null || t == null ? null : (u, t);
  }

  Future<void> clear() async {
    await storage.deleteAll();
    await clearParticipantCache(await SharedPreferences.getInstance());
  }
}

final _store = SessionStore(FlutterSecureStorage());
void main() => runApp(ParticipantApp());

final participantTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: const Color(0xFF215BB3),
    primary: const Color(0xFF215BB3),
    secondary: const Color(0xFFC66A2F),
    surface: const Color(0xFFF8FAFD),
  ),
  scaffoldBackgroundColor: const Color(0xFFF4F7FB),
  inputDecorationTheme: const InputDecorationTheme(
    border: OutlineInputBorder(),
    filled: true,
    fillColor: Colors.white,
  ),
  cardTheme: const CardThemeData(
    elevation: 0,
    margin: EdgeInsets.symmetric(vertical: 6),
  ),
);

class ParticipantApp extends StatefulWidget {
  ParticipantApp({super.key, SessionStore? store, this.factory})
    : store = store ?? _store;
  final SessionStore store;
  final ParticipantApi Function(String, String?)? factory;
  @override
  State<ParticipantApp> createState() => _ParticipantAppState();
}

class _ParticipantAppState extends State<ParticipantApp> {
  ParticipantApi? api;
  Map<String, dynamic>? session;
  List<Map<String, dynamic>> studyDocuments = [];
  List<Map<String, dynamic>> availableStudies = [];
  bool busy = true, documentsLoading = false;
  String? error, documentsError, studySwitchError;
  ParticipantApi make(String u, String? t) =>
      widget.factory?.call(u, t) ?? Api(Uri.parse(u), t);
  @override
  void initState() {
    super.initState();
    restore();
  }

  Future<void> loadStudyDocuments() async {
    if (!invitationRequiresStudyDocuments(session)) {
      studyDocuments = [];
      documentsError = null;
      return;
    }
    documentsLoading = true;
    documentsError = null;
    if (mounted) setState(() {});
    try {
      final result = await api!.legalDocuments();
      final documents = (result['documents'] as List? ?? const [])
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
      final types = documents
          .map((item) => item['document_type'].toString())
          .toSet();
      if (!types.containsAll({
        'participant_information',
        'privacy_notice',
        'consent_text',
      }))
        throw const ApiError('The study consent documents are incomplete.');
      studyDocuments = documents;
    } on ApiError catch (_) {
      studyDocuments = [];
      documentsError = 'We could not load this study’s consent documents. Your consent has not been submitted.';
    } catch (_) {
      studyDocuments = [];
      documentsError = 'We could not load this study’s consent documents. Your consent has not been submitted.';
    }
    documentsLoading = false;
    if (mounted) setState(() {});
  }

  Future<void> refreshSession() async {
    session = await api!.session();
    if (invitationRequiresConsent(session)) {
      availableStudies = [];
      await loadStudyDocuments();
    } else {
      studyDocuments = [];
      documentsError = null;
      try {
        availableStudies = await api!.availableStudies();
        studySwitchError = null;
      } catch (error) {
        availableStudies = [];
        studySwitchError = availableStudiesLoadError(error);
      }
    }
  }

  Future<void> restore() async {
    try {
      final saved = await widget.store.read();
      if (saved != null) {
        api = make(saved.$1, saved.$2);
        await refreshSession();
      }
    } catch (_) {
      try {
        await widget.store.clear();
      } catch (_) {
        // A device keychain failure must not trap a participant on a spinner.
      }
      api = null;
      session = null;
      availableStudies = [];
    }
    if (mounted) setState(() => busy = false);
  }

  Future<void> join(String invitation) async {
    final codeError = invitationCodeError(invitation);
    if (codeError != null) {
      error = codeError;
      if (mounted) setState(() {});
      return;
    }
    final base = configuredApiBase();
    if (base == null) {
      error = 'This app is not configured to connect securely. Please contact your research team.';
      if (mounted) setState(() {});
      return;
    }
    try {
      final first = make(base.toString(), null);
      final result = await first.exchange(invitation.trim());
      final token = (result['session'] as Map)['access_token'] as String;
      await widget.store.save(base.toString(), token);
      api = make(base.toString(), token);
      await refreshSession();
      error = null;
    } on ApiError catch (e) {
      error = e.message;
    } catch (_) {
      error = 'We could not connect. Please try again.';
    }
    if (mounted) setState(() {});
  }

  Future<void> accept(Map<String, String> documentHashes) async {
    try {
      await api!.consent(documentHashes);
      await refreshSession();
      error = null;
    } on ApiError catch (e) {
      error = e.message;
    }
    if (mounted) setState(() {});
  }

  Future<void> signOut() async {
    try {
      await api?.logout();
    } catch (_) {}
    await widget.store.clear();
    if (mounted)
      setState(() {
        api = null;
        session = null;
        availableStudies = [];
        error = null;
      });
  }

  Future<void> switchStudy(int studyId) async {
    final currentStudyId =
        (session?['invitation'] as Map?)?['study_id'] as int?;
    if (api == null || currentStudyId == studyId) return;
    if (!availableStudies.any((study) => study['study_id'] == studyId)) {
      studySwitchError = 'That study is not available in your secure session.';
      if (mounted) setState(() {});
      return;
    }
    try {
      final switched = await api!.switchStudy(studyId);
      final token = (switched['session'] as Map?)?['access_token']?.toString();
      final saved = await widget.store.read();
      if (token == null || token.isEmpty || saved == null)
        throw const ApiError('Your secure session could not be changed.');
      await widget.store.save(saved.$1, token);
      api = make(saved.$1, token);
      await refreshSession();
      error = null;
    } on ApiError catch (e) {
      if (e.category == 'session_ended') {
        await signOut();
        return;
      }
      studySwitchError = e.message;
    } catch (_) {
      studySwitchError = 'Your study could not be changed. Please try again.';
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext c) {
    if (busy)
      return const MaterialApp(
        home: Scaffold(
          body: Center(
            child: CircularProgressIndicator(
              semanticsLabel: 'Loading your secure session',
            ),
          ),
        ),
      );
    if (api == null)
      return MaterialApp(
        theme: participantTheme,
        home: Invite(error: error, onJoin: join),
      );
    final participant = Map<String, dynamic>.from(session!['participant']);
    if (invitationRequiresConsent(session))
      return MaterialApp(
        theme: participantTheme,
        home: Consent(
          error: error,
          documents: studyDocuments,
          documentsRequired: invitationRequiresStudyDocuments(session),
          documentsLoading: documentsLoading,
          documentsError: documentsError,
          onRetry: loadStudyDocuments,
          onAccept: accept,
        ),
      );
    final activeStudyId = (session!['invitation'] as Map?)?['study_id'] as int?;
    return MaterialApp(
      theme: participantTheme,
      home: Home(
        key: ValueKey('study-$activeStudyId'),
        api: api! as Api,
        name: participant['display_name'] as String,
        onLogout: signOut,
        studies: availableStudies,
        activeStudyId: activeStudyId,
        studySwitchError: studySwitchError,
        onSwitchStudy: switchStudy,
      ),
    );
  }
}

String availableStudiesLoadError(Object error) {
  if (error is ApiError && error.statusCode == 409) {
    return 'Your study access needs review. You can continue using your current study, but switching studies is temporarily unavailable. Please contact the research team.';
  }
  return 'Your available studies could not be loaded. You can keep using this study.';
}

class Invite extends StatefulWidget {
  const Invite({super.key, required this.error, required this.onJoin});
  final String? error;
  final Future<void> Function(String) onJoin;
  @override
  State<Invite> createState() => _InviteState();
}

class _InviteState extends State<Invite> {
  final code = TextEditingController();
  bool waiting = false;
  @override
  void dispose() {
    code.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    setState(() => waiting = true);
    await widget.onJoin(code.text.trim());
    if (mounted) setState(() => waiting = false);
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    backgroundColor: const Color(0xFF174A8B),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 28, 20, 28),
            shrinkWrap: true,
            children: [
              Semantics(
                image: true,
                label: 'Citizen Centric by Politis',
                child: ColorFiltered(
                  colorFilter: const ColorFilter.mode(
                    Colors.white,
                    BlendMode.srcIn,
                  ),
                  child: Image.asset(
                    'assets/citizen-centric-logo.png',
                    height: 68,
                    fit: BoxFit.contain,
                  ),
                ),
              ),
              const SizedBox(height: 28),
              Card(
                color: Colors.white,
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Semantics(
                        header: true,
                        child: const Text(
                          'Join your study',
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        'After reviewing and consenting on the secure website, enter the one-time app code shown in your participant portal.',
                      ),
                      const SizedBox(height: 20),
                      TextField(
                        controller: code,
                        autofillHints: const [AutofillHints.oneTimeCode],
                        textCapitalization: TextCapitalization.characters,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => submit(),
                        decoration: const InputDecoration(
                          labelText: 'One-time app code',
                          hintText: 'CC-XXXX-XXXX-XXXX-XXXX',
                        ),
                      ),
                      if (widget.error != null)
                        Semantics(
                          liveRegion: true,
                          container: true,
                          child: Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(
                              widget.error!,
                              style: const TextStyle(color: Colors.red),
                            ),
                          ),
                        ),
                      const SizedBox(height: 20),
                      SizedBox(
                        height: 50,
                        child: FilledButton(
                          onPressed: waiting ? null : submit,
                          child: Text(
                            waiting ? 'Checking code…' : 'Continue securely',
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 18),
              const Text(
                'Your code is single-use and expires after 30 minutes.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white70),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class Consent extends StatefulWidget {
  const Consent({
    super.key,
    required this.error,
    required this.documents,
    required this.documentsRequired,
    required this.documentsLoading,
    required this.documentsError,
    required this.onRetry,
    required this.onAccept,
  });
  final String? error, documentsError;
  final List<Map<String, dynamic>> documents;
  final bool documentsRequired, documentsLoading;
  final Future<void> Function() onRetry;
  final Future<void> Function(Map<String, String>) onAccept;
  @override
  State<Consent> createState() => _ConsentState();
}

class _ConsentState extends State<Consent> {
  bool yes = false, waiting = false;
  final reviewed = <String>{};
  Future<void> go() async {
    setState(() => waiting = true);
    await widget.onAccept({
      for (final document in widget.documents)
        document['document_type'].toString(): document['content_sha256']
            .toString(),
    });
    if (mounted) setState(() => waiting = false);
  }

  @override
  Widget build(BuildContext c) {
    const boundTypes = {
      'participant_information',
      'privacy_notice',
      'consent_text',
    };
    final types = widget.documents
        .map((document) => document['document_type'].toString())
        .toSet();
    final documentsReady =
        !widget.documentsRequired || types.containsAll(boundTypes);
    final requiredTypes = widget.documentsRequired ? boundTypes : types;
    final canAccept =
        yes &&
        documentsReady &&
        requiredTypes.difference(reviewed).isEmpty &&
        !waiting;
    return Scaffold(
      appBar: AppBar(title: const Text('Your consent')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: ListView(
          children: [
            Semantics(
              header: true,
              child: const Text(
                'Before you begin',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
              ),
            ),
            const Text(
              'Taking part is your choice. Review the exact study documents bound to your invitation before you decide.',
            ),
            if (widget.documentsLoading)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Center(
                  child: CircularProgressIndicator(
                    semanticsLabel: 'Loading study consent documents',
                  ),
                ),
              ),
            if (widget.documentsError != null) ...[
              Semantics(
                liveRegion: true,
                child: Text(
                  widget.documentsError!,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
              TextButton(
                onPressed: widget.documentsLoading ? null : widget.onRetry,
                child: const Text('Try again'),
              ),
            ],
            ...widget.documents.map(
              (document) => TextButton.icon(
                onPressed: () =>
                    Navigator.push(
                      c,
                      MaterialPageRoute(
                        builder: (_) =>
                            StudyConsentDocumentScreen(document: document),
                      ),
                    ).then(
                      (_) => setState(
                        () =>
                            reviewed.add(document['document_type'].toString()),
                      ),
                    ),
                icon: const Icon(Icons.article_outlined),
                label: Text(
                  'Read ${document['title']} (version ${document['version']})',
                ),
              ),
            ),
            if (widget.documents.isEmpty && !widget.documentsRequired)
              TextButton.icon(
                onPressed: () => Navigator.push(
                  c,
                  MaterialPageRoute(
                    builder: (_) => LegalDocumentScreen(
                      document: participantInformationDocument,
                    ),
                  ),
                ),
                icon: const Icon(Icons.article_outlined),
                label: const Text('Read participant information'),
              ),
            CheckboxListTile(
              value: yes,
              onChanged: (v) => setState(() => yes = v ?? false),
              title: const Text('I understand and agree to take part.'),
              controlAffinity: ListTileControlAffinity.leading,
            ),
            if (widget.error != null)
              Semantics(
                liveRegion: true,
                child: Text(
                  widget.error!,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            SizedBox(
              height: 48,
              child: FilledButton(
                onPressed: canAccept ? go : null,
                child: Text(
                  waiting ? 'Saving consent…' : 'Accept and continue',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class StudyConsentDocumentScreen extends StatelessWidget {
  const StudyConsentDocumentScreen({super.key, required this.document});
  final Map<String, dynamic> document;
  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(
      title: Text(document['title']?.toString() ?? 'Study document'),
    ),
    body: Padding(
      padding: const EdgeInsets.all(24),
      child: ListView(
        children: [
          Semantics(
            header: true,
            child: Text(
              document['title']?.toString() ?? 'Study document',
              style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
            ),
          ),
          Text(
            'Version ${document['version']} · ${document['effective_date']}',
          ),
          Text('Reference: ${document['reference']}'),
          const SizedBox(height: 20),
          SelectableText(document['body']?.toString() ?? ''),
        ],
      ),
    ),
  );
}

class Home extends StatefulWidget {
  const Home({
    super.key,
    required this.api,
    required this.name,
    required this.onLogout,
    this.studies = const [],
    this.activeStudyId,
    this.studySwitchError,
    this.onSwitchStudy,
    this.dashboardLoader,
  });
  final Api api;
  final String name;
  final Future<void> Function() onLogout;
  final List<Map<String, dynamic>> studies;
  final int? activeStudyId;
  final String? studySwitchError;
  final Future<void> Function(int studyId)? onSwitchStudy;
  final Future<Map<String, dynamic>> Function()? dashboardLoader;
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  late Future<Map<String, dynamic>> load;

  @override
  void initState() {
    super.initState();
    load = refresh();
  }

  Future<Map<String, dynamic>> refresh() async {
    if (widget.dashboardLoader != null) return widget.dashboardLoader!();
    await Queue.replay(widget.api, studyId: widget.activeStudyId);
    await MediaQueue.replay(widget.api, studyId: widget.activeStudyId);
    await EvidenceReceiptStore.refresh(
      widget.api,
      studyId: widget.activeStudyId,
    );
    final portal = await widget.api.portal();
    final pending = await MediaQueue.count(studyId: widget.activeStudyId);
    return {...portal, 'pending_uploads': pending};
  }

  Future<void> open(Widget page) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => page));
    if (mounted) setState(() => load = refresh());
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(
      title: const Text('Citizen Centric'),
      actions: [
        if (widget.studies.length > 1 && widget.onSwitchStudy != null)
          PopupMenuButton<int>(
            tooltip: 'Switch study',
            onSelected: widget.onSwitchStudy,
            itemBuilder: (context) => widget.studies
                .map(
                  (study) => PopupMenuItem<int>(
                    value: study['study_id'] as int,
                    enabled: study['study_id'] != widget.activeStudyId,
                    child: Text(study['title']?.toString() ?? 'Study'),
                  ),
                )
                .toList(),
            child: const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Row(
                children: [
                  Icon(Icons.school_outlined),
                  SizedBox(width: 4),
                  Text('My studies'),
                ],
              ),
            ),
          ),
        IconButton(
          tooltip: 'Sign out',
          onPressed: widget.onLogout,
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: FutureBuilder<Map<String, dynamic>>(
      future: load,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          if (snapshot.hasError) {
            return Center(
              child: FilledButton(
                onPressed: () => setState(() => load = refresh()),
                child: const Text('Try again'),
              ),
            );
          }
          return const Center(
            child: CircularProgressIndicator(
              semanticsLabel: 'Loading your study dashboard',
            ),
          );
        }
        final data = snapshot.data!;
        final study = Map<String, dynamic>.from(data['study'] as Map);
        final activities = data['activities'] as List? ?? const [];
        final outstanding = activities.where((item) {
          if ((item as Map)['allow_multiple_entries'] == true) return true;
          final response = item['response'];
          return response is! Map || response['status'] != 'submitted';
        }).length;
        final messages = data['messages'] as List? ?? const [];
        final pending = data['pending_uploads'] as int? ?? 0;
        return RefreshIndicator(
          onRefresh: () async => setState(() => load = refresh()),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 18, 16, 32),
            children: [
              if (widget.studySwitchError != null)
                Semantics(
                  liveRegion: true,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      widget.studySwitchError!,
                      style: const TextStyle(color: Color(0xFF9C2C21)),
                    ),
                  ),
                ),
              Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(24),
                  gradient: const LinearGradient(
                    colors: [Color(0xFF174A8B), Color(0xFF215BB3)],
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Semantics(
                      header: true,
                      child: Text(
                        'Welcome, ${widget.name}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 26,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      study['title']?.toString() ?? 'Your study',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 19,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if ((study['description']?.toString() ?? '')
                        .isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        study['description'].toString(),
                        style: const TextStyle(color: Colors.white70),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  _DashboardMetric(
                    icon: Icons.assignment_outlined,
                    value: '$outstanding',
                    label: 'to complete',
                  ),
                  _DashboardMetric(
                    icon: Icons.forum_outlined,
                    value: '${messages.length}',
                    label: 'messages',
                  ),
                  _DashboardMetric(
                    icon: Icons.cloud_upload_outlined,
                    value: '$pending',
                    label: pending == 1 ? 'upload pending' : 'uploads pending',
                  ),
                ],
              ),
              const SizedBox(height: 16),
              _DashboardLink(
                icon: Icons.assignment_outlined,
                title: 'Activities',
                subtitle: '$outstanding awaiting completion',
                onTap: () => open(
                  Activities(api: widget.api, studyId: widget.activeStudyId),
                ),
              ),
              _DashboardLink(
                icon: Icons.history,
                title: 'Submission history',
                subtitle: 'Review answers and uploaded evidence',
                onTap: () => open(
                  History(api: widget.api, studyId: widget.activeStudyId),
                ),
              ),
              _DashboardLink(
                icon: Icons.forum_outlined,
                title: 'Messages',
                subtitle: 'Talk securely with your research team',
                onTap: () => open(
                  Messages(api: widget.api, studyId: widget.activeStudyId),
                ),
              ),
              _DashboardLink(
                icon: Icons.person_outline,
                title: 'Profile and contact preferences',
                onTap: () => open(
                  Profile(api: widget.api, studyId: widget.activeStudyId),
                ),
              ),
              _DashboardLink(
                icon: Icons.privacy_tip_outlined,
                title: 'Legal and privacy',
                subtitle: 'Your information, choices and account',
                onTap: () => open(
                  LegalPrivacyCentre(
                    onOpenPrivacyChoices: () => Navigator.push(
                      c,
                      MaterialPageRoute(
                        builder: (_) => PrivacyChoices(
                          api: widget.api,
                          onSessionEnded: widget.onLogout,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    ),
  );
}

class _DashboardMetric extends StatelessWidget {
  const _DashboardMetric({
    required this.icon,
    required this.value,
    required this.label,
  });
  final IconData icon;
  final String value;
  final String label;
  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(minWidth: 104),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: const Color(0xFFD8E1ED)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: const Color(0xFF215BB3)),
        const SizedBox(height: 6),
        Text(
          value,
          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    ),
  );
}

class _DashboardLink extends StatelessWidget {
  const _DashboardLink({
    required this.icon,
    required this.title,
    this.subtitle,
    required this.onTap,
  });
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(
    color: Colors.white,
    child: ListTile(
      minTileHeight: 72,
      leading: CircleAvatar(
        backgroundColor: const Color(0xFFE8F0FC),
        foregroundColor: const Color(0xFF174A8B),
        child: Icon(icon),
      ),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: subtitle == null ? null : Text(subtitle!),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    ),
  );
}

enum SyncState { waiting, sending, sent, needsAttention }

class Queue {
  static const _key = 'submission_queue';
  static Future<void> add(Map<String, dynamic> entry) async {
    final p = await SharedPreferences.getInstance();
    final rows = p.getStringList(_key) ?? [];
    if (rows.any(
      (row) => jsonDecode(row)['idempotency_key'] == entry['idempotency_key'],
    ))
      return;
    rows.add(
      jsonEncode({
        ...entry,
        'attempts': 0,
        'next_attempt_at': DateTime.now().toIso8601String(),
      }),
    );
    await p.setStringList(_key, rows);
  }

  static Future<int> count({int? studyId}) async {
    final rows =
        (await SharedPreferences.getInstance()).getStringList(_key) ?? const [];
    if (studyId == null) return rows.length;
    return rows.where((row) {
      try {
        return (jsonDecode(row) as Map)['study_id'] == studyId;
      } catch (_) {
        return false;
      }
    }).length;
  }

  static Duration backoff(int attempts) =>
      Duration(seconds: (1 << attempts.clamp(0, 6)));
  static Future<SyncState> replay(
    Api api, {
    DateTime? now,
    int? studyId,
  }) async {
    final p = await SharedPreferences.getInstance();
    final rows = p.getStringList(_key) ?? [];
    final retained = <String>[];
    var state = SyncState.sent;
    final clock = now ?? DateTime.now();
    for (final row in rows) {
      Map<String, dynamic> item;
      try {
        item = Map<String, dynamic>.from(jsonDecode(row));
      } catch (_) {
        retained.add(row);
        state = SyncState.needsAttention;
        continue;
      }
      if (studyId != null && item['study_id'] == null) {
        // Pre-namespacing queue rows were created by the currently active
        // study session. Bind them once before any study switch is offered.
        item['study_id'] = studyId;
      }
      if (studyId != null && item['study_id'] != studyId) {
        retained.add(row);
        continue;
      }
      final due = DateTime.tryParse(item['next_attempt_at'] ?? '') ?? clock;
      if (due.isAfter(clock)) {
        retained.add(jsonEncode(item));
        state = SyncState.waiting;
        continue;
      }
      try {
        await api.submitResponse(
          item['activity_id'] as int,
          item['idempotency_key'] as String,
          answer: item['answer']?.toString(),
          choices: (item['choices'] as List? ?? const [])
              .whereType<String>()
              .toList(),
          location: item['location'] is Map
              ? Map<String, dynamic>.from(item['location'] as Map)
              : null,
        );
      } on ApiError catch (e) {
        if (e.message == 'Your session has ended.') {
          retained.add(row);
          state = SyncState.needsAttention;
        } else {
          final attempts = (item['attempts'] as int? ?? 0) + 1;
          item['attempts'] = attempts;
          item['next_attempt_at'] = clock
              .add(backoff(attempts))
              .toIso8601String();
          retained.add(jsonEncode(item));
          state = SyncState.waiting;
        }
      } catch (_) {
        final attempts = (item['attempts'] as int? ?? 0) + 1;
        item['attempts'] = attempts;
        item['next_attempt_at'] = clock
            .add(backoff(attempts))
            .toIso8601String();
        retained.add(jsonEncode(item));
        state = SyncState.waiting;
      }
    }
    await p.setStringList(_key, retained);
    return state;
  }
}

class PendingMediaUpload {
  const PendingMediaUpload({
    required this.activityId,
    this.studyId,
    required this.localPath,
    required this.filename,
    required this.kind,
    required this.contentType,
    required this.idempotencyKey,
    required this.attempts,
    required this.nextAttemptAt,
    this.failureCategory,
  });

  final int activityId;
  final int? studyId;
  final String localPath;
  final String filename;
  final String kind;
  final String contentType;
  final String idempotencyKey;
  final int attempts;
  final DateTime nextAttemptAt;
  final String? failureCategory;

  Map<String, dynamic> toJson() => {
    'activity_id': activityId,
    if (studyId != null) 'study_id': studyId,
    'local_path': localPath,
    'filename': filename,
    'kind': kind,
    'content_type': contentType,
    'idempotency_key': idempotencyKey,
    'attempts': attempts,
    'next_attempt_at': nextAttemptAt.toIso8601String(),
    if (failureCategory != null) 'failure_category': failureCategory,
  };

  factory PendingMediaUpload.fromJson(Map<String, dynamic> value) =>
      PendingMediaUpload(
        activityId: value['activity_id'] as int,
        studyId: value['study_id'] as int?,
        localPath: value['local_path'] as String,
        filename: value['filename'] as String,
        kind: value['kind'] as String,
        contentType: value['content_type'] as String,
        idempotencyKey: value['idempotency_key'] as String,
        attempts: value['attempts'] as int? ?? 0,
        nextAttemptAt:
            DateTime.tryParse(value['next_attempt_at']?.toString() ?? '') ??
            DateTime.now(),
        failureCategory: value['failure_category'] as String?,
      );

  PendingMediaUpload retryAt(DateTime value) => PendingMediaUpload(
    activityId: activityId,
    studyId: studyId,
    localPath: localPath,
    filename: filename,
    kind: kind,
    contentType: contentType,
    idempotencyKey: idempotencyKey,
    attempts: attempts + 1,
    nextAttemptAt: value,
    failureCategory: failureCategory,
  );

  PendingMediaUpload blocked(String category) => PendingMediaUpload(
    activityId: activityId,
    studyId: studyId,
    localPath: localPath,
    filename: filename,
    kind: kind,
    contentType: contentType,
    idempotencyKey: idempotencyKey,
    attempts: attempts,
    nextAttemptAt: nextAttemptAt,
    failureCategory: category,
  );

  PendingMediaUpload forStudy(int value) => PendingMediaUpload(
    activityId: activityId,
    studyId: value,
    localPath: localPath,
    filename: filename,
    kind: kind,
    contentType: contentType,
    idempotencyKey: idempotencyKey,
    attempts: attempts,
    nextAttemptAt: nextAttemptAt,
    failureCategory: failureCategory,
  );
}

class EvidenceReceiptStore {
  static const _key = 'evidence_receipts';

  static Future<List<Map<String, dynamic>>> read({int? studyId}) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null) return [];
    try {
      final rows = (jsonDecode(raw) as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
      return studyId == null
          ? rows
          : rows.where((item) => item['study_id'] == studyId).toList();
    } catch (_) {
      await prefs.remove(_key);
      return [];
    }
  }

  static Future<void> record(
    int activityId,
    Map<String, dynamic> evidence, {
    int? studyId,
  }) async {
    final rows = await read();
    final id = evidence['evidence_id'];
    rows.removeWhere((item) => item['evidence_id'] == id);
    rows.add({
      ...evidence,
      'activity_id': activityId,
      if (studyId != null) 'study_id': studyId,
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(rows));
  }

  static Future<List<Map<String, dynamic>>> refresh(
    Api api, {
    int? studyId,
  }) async {
    final rows = await read();
    for (var index = 0; index < rows.length; index++) {
      final row = rows[index];
      if (studyId != null && row['study_id'] == null) {
        row['study_id'] = studyId;
      }
      if (studyId != null && row['study_id'] != studyId) continue;
      if (row['scan_status'] != 'pending') continue;
      try {
        final result = await api.evidenceStatus(row['evidence_id'] as int);
        rows[index] = {
          ...Map<String, dynamic>.from(result['evidence'] as Map),
          if (row['study_id'] != null) 'study_id': row['study_id'],
        };
      } catch (_) {
        // A transient status failure must not discard the server acknowledgement.
      }
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(rows));
    return rows;
  }
}

class MediaQueue {
  static const _key = 'media_upload_queue';

  static Future<List<PendingMediaUpload>> read() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_key) ?? [];
    final valid = <PendingMediaUpload>[];
    for (final item in raw) {
      try {
        valid.add(
          PendingMediaUpload.fromJson(
            Map<String, dynamic>.from(jsonDecode(item) as Map),
          ),
        );
      } catch (_) {
        // Keep malformed rows fail-closed so logout can remove them.
      }
    }
    return valid;
  }

  static Future<PendingMediaUpload> enqueue({
    required int activityId,
    int? studyId,
    required String sourcePath,
    required String filename,
    required String kind,
    Directory? supportDirectory,
  }) async {
    final directory =
        supportDirectory ?? await getApplicationSupportDirectory();
    final pendingDirectory = Directory('${directory.path}/pending-media');
    await pendingDirectory.create(recursive: true);
    final key = const Uuid().v4();
    final extension = filename.contains('.')
        ? '.${filename.split('.').last}'
        : '';
    final durable = File('${pendingDirectory.path}/$key$extension');
    await File(sourcePath).copy(durable.path);
    final item = PendingMediaUpload(
      activityId: activityId,
      studyId: studyId,
      localPath: durable.path,
      filename: filename,
      kind: kind,
      contentType: mediaContentType(filename, kind),
      idempotencyKey: key,
      attempts: 0,
      nextAttemptAt: DateTime.now(),
      failureCategory: null,
    );
    final prefs = await SharedPreferences.getInstance();
    final rows = prefs.getStringList(_key) ?? [];
    rows.add(jsonEncode(item.toJson()));
    await prefs.setStringList(_key, rows);
    return item;
  }

  static Future<int> count({int? studyId}) async {
    final rows = await read();
    return studyId == null
        ? rows.length
        : rows.where((item) => item.studyId == studyId).length;
  }

  static Future<PendingMediaUpload?> pendingFor(
    int activityId,
    String kind, {
    int? studyId,
  }) async {
    for (final item in (await read()).reversed) {
      if (item.activityId == activityId &&
          item.kind == kind &&
          (studyId == null ||
              item.studyId == null ||
              item.studyId == studyId)) {
        return item;
      }
    }
    return null;
  }

  static Future<void> remove(String idempotencyKey) async {
    final rows = await read();
    final removed = rows.where((item) => item.idempotencyKey == idempotencyKey);
    for (final item in removed) {
      final file = File(item.localPath);
      if (await file.exists()) await file.delete();
    }
    final retained = rows.where(
      (item) => item.idempotencyKey != idempotencyKey,
    );
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _key,
      retained.map((item) => jsonEncode(item.toJson())).toList(),
    );
  }

  static Future<SyncState> replay(
    Api api, {
    DateTime? now,
    int? studyId,
    String? onlyKey,
    Future<Map<String, dynamic>> Function(PendingMediaUpload)? uploader,
  }) async {
    final clock = now ?? DateTime.now();
    final retained = <PendingMediaUpload>[];
    var state = SyncState.sent;
    for (final storedItem in await read()) {
      final item = studyId != null && storedItem.studyId == null
          ? storedItem.forStudy(studyId)
          : storedItem;
      if (studyId != null && item.studyId != studyId) {
        retained.add(item);
        continue;
      }
      if (item.failureCategory != null) {
        retained.add(item);
        state = SyncState.needsAttention;
        continue;
      }
      if ((onlyKey != null && item.idempotencyKey != onlyKey) ||
          item.nextAttemptAt.isAfter(clock)) {
        retained.add(item);
        state = SyncState.waiting;
        continue;
      }
      try {
        final result =
            await (uploader?.call(item) ??
                api.uploadEvidence(
                  item.activityId,
                  item.localPath,
                  item.filename,
                  item.contentType,
                  item.idempotencyKey,
                ));
        final evidence = Map<String, dynamic>.from(result['evidence'] as Map);
        await EvidenceReceiptStore.record(
          item.activityId,
          evidence,
          studyId: item.studyId,
        );
        final local = File(item.localPath);
        if (await local.exists()) await local.delete();
      } on ApiError catch (error) {
        if (!error.retryable) {
          retained.add(item.blocked(error.category ?? 'security_rejected'));
          state = SyncState.needsAttention;
        } else if (error.message == 'Your session has ended.') {
          retained.add(item);
          state = SyncState.needsAttention;
        } else {
          retained.add(
            item.retryAt(clock.add(Queue.backoff(item.attempts + 1))),
          );
          state = SyncState.waiting;
        }
      } catch (_) {
        retained.add(item.retryAt(clock.add(Queue.backoff(item.attempts + 1))));
        state = SyncState.waiting;
      }
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _key,
      retained.map((item) => jsonEncode(item.toJson())).toList(),
    );
    return state;
  }
}

bool activityIsSubmitted(Map<String, dynamic> activity) {
  if (activity['allow_multiple_entries'] == true) return false;
  final response = activity['response'];
  return response is Map && response['status'] == 'submitted';
}

String activityRendererName(String? activityType) => switch (activityType) {
  'short_text' => 'short_text',
  'long_text' => 'long_text',
  'single_choice' => 'single_choice',
  'multiple_choice' => 'multiple_choice',
  'rating' => 'rating',
  'slider' => 'slider',
  'photo' => 'photo',
  'audio' => 'audio',
  'video' => 'video',
  'gps' => 'gps',
  'ranking' => 'ranking',
  'file' => 'file',
  _ => 'unsupported',
};

Widget participantActivityPage(
  Api api,
  Map<String, dynamic> item, {
  int? studyId,
}) {
  final activityId = item['activity_id'] as int;
  final submitted = activityIsSubmitted(item);
  switch (activityRendererName(item['activity_type']?.toString())) {
    case 'short_text':
      return TextActivity(
        api: api,
        item: item,
        studyId: studyId,
        singleLine: true,
      );
    case 'long_text':
      return TextActivity(api: api, item: item, studyId: studyId);
    case 'single_choice':
    case 'multiple_choice':
      return ChoiceActivity(api: api, item: item, studyId: studyId);
    case 'rating':
      return RatingActivity(api: api, item: item, studyId: studyId);
    case 'slider':
      return SliderActivity(api: api, item: item, studyId: studyId);
    case 'ranking':
      return RankingActivity(api: api, item: item, studyId: studyId);
    case 'photo':
      return PhotoEvidence(
        api: api,
        activityId: activityId,
        studyId: studyId,
        title: item['title']?.toString(),
        prompt: item['prompt']?.toString(),
        submitted: submitted,
      );
    case 'audio':
      return VoiceDiary(
        api: api,
        activityId: activityId,
        studyId: studyId,
        title: item['title']?.toString(),
        prompt: item['prompt']?.toString(),
        submitted: submitted,
      );
    case 'video':
      return VideoEvidence(
        api: api,
        activityId: activityId,
        studyId: studyId,
        title: item['title']?.toString(),
        prompt: item['prompt']?.toString(),
        submitted: submitted,
      );
    case 'gps':
      return LocationActivity(api: api, item: item, studyId: studyId);
    case 'file':
      return DocumentEvidence(
        api: api,
        activityId: activityId,
        studyId: studyId,
        title: item['title']?.toString(),
        prompt: item['prompt']?.toString(),
        submitted: submitted,
      );
    default:
      return UnsupportedActivity(item: item);
  }
}

class UnsupportedActivity extends StatelessWidget {
  const UnsupportedActivity({super.key, required this.item});
  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(item['title']?.toString() ?? 'Activity')),
    body: const Padding(
      padding: EdgeInsets.all(24),
      child: Text(
        "This activity type isn't supported by this version of the app.",
      ),
    ),
  );
}

enum StructuredControl { singleChoice, multipleChoice, rating, slider, ranking }

class ChoiceActivity extends StatelessWidget {
  const ChoiceActivity({
    super.key,
    required this.api,
    required this.item,
    this.studyId,
  });
  final Api api;
  final Map<String, dynamic> item;
  final int? studyId;
  @override
  Widget build(BuildContext context) => StructuredResponseActivity(
    api: api,
    item: item,
    studyId: studyId,
    control: item['activity_type'] == 'single_choice'
        ? StructuredControl.singleChoice
        : StructuredControl.multipleChoice,
  );
}

class RatingActivity extends StatelessWidget {
  const RatingActivity({
    super.key,
    required this.api,
    required this.item,
    this.studyId,
  });
  final Api api;
  final Map<String, dynamic> item;
  final int? studyId;
  @override
  Widget build(BuildContext context) => StructuredResponseActivity(
    api: api,
    item: item,
    studyId: studyId,
    control: StructuredControl.rating,
  );
}

class SliderActivity extends StatelessWidget {
  const SliderActivity({
    super.key,
    required this.api,
    required this.item,
    this.studyId,
  });
  final Api api;
  final Map<String, dynamic> item;
  final int? studyId;
  @override
  Widget build(BuildContext context) => StructuredResponseActivity(
    api: api,
    item: item,
    studyId: studyId,
    control: StructuredControl.slider,
  );
}

class RankingActivity extends StatelessWidget {
  const RankingActivity({
    super.key,
    required this.api,
    required this.item,
    this.studyId,
  });
  final Api api;
  final Map<String, dynamic> item;
  final int? studyId;
  @override
  Widget build(BuildContext context) => StructuredResponseActivity(
    api: api,
    item: item,
    studyId: studyId,
    control: StructuredControl.ranking,
  );
}

class StructuredResponseActivity extends StatefulWidget {
  const StructuredResponseActivity({
    super.key,
    required this.api,
    required this.item,
    required this.control,
    this.studyId,
  });
  final Api api;
  final Map<String, dynamic> item;
  final StructuredControl control;
  final int? studyId;
  @override
  State<StructuredResponseActivity> createState() =>
      _StructuredResponseActivityState();
}

class _StructuredResponseActivityState
    extends State<StructuredResponseActivity> {
  late bool submitted;
  late String entryKey;
  String? answer;
  List<String> choices = [];
  bool working = false;
  String status = '';

  List<String> get options => (widget.item['options'] as List? ?? const [])
      .whereType<String>()
      .map((value) => value.trim())
      .where((value) => value.isNotEmpty)
      .toList();
  String get draftKey =>
      activityDraftKey(widget.item['activity_id'] as int, widget.studyId);
  bool get repeatable => widget.item['allow_multiple_entries'] == true;

  @override
  void initState() {
    super.initState();
    submitted = activityIsSubmitted(widget.item);
    entryKey = const Uuid().v4();
    if (widget.control == StructuredControl.ranking) choices = [...options];
    restore();
  }

  Future<void> restore() async {
    final saved = await readActivityDraft(
      widget.item['activity_id'] as int,
      widget.studyId,
    );
    if (saved == null) return;
    try {
      final value = Map<String, dynamic>.from(jsonDecode(saved) as Map);
      final storedChoices = (value['choices'] as List? ?? const [])
          .whereType<String>()
          .toList();
      final validChoices =
          storedChoices.length == storedChoices.toSet().length &&
          storedChoices.every(options.contains);
      if (validChoices) {
        if (widget.control == StructuredControl.ranking &&
            storedChoices.length == options.length &&
            storedChoices.toSet().containsAll(options)) {
          choices = storedChoices;
        } else if (widget.control != StructuredControl.ranking) {
          choices = storedChoices;
        }
      }
      final storedAnswer = value['answer']?.toString();
      if (storedAnswer != null && options.contains(storedAnswer)) {
        answer = storedAnswer;
      }
      entryKey = value['idempotency_key']?.toString() ?? entryKey;
    } catch (_) {
      // Invalid local structured data is ignored rather than submitted.
    }
    if (mounted) setState(() {});
  }

  Future<void> persist() async {
    await (await SharedPreferences.getInstance()).setString(
      draftKey,
      jsonEncode({
        'answer': answer,
        'choices': choices,
        'idempotency_key': entryKey,
        if (widget.studyId != null) 'study_id': widget.studyId,
      }),
    );
  }

  String? validate(bool submit) {
    if (options.length < 2 || options.length != options.toSet().length) {
      return 'This activity is not configured safely. Please contact the research team.';
    }
    if (widget.control == StructuredControl.ranking) {
      if (choices.length != options.length ||
          choices.length != choices.toSet().length ||
          !choices.toSet().containsAll(options)) {
        return 'Rank every option exactly once before submitting.';
      }
      return null;
    }
    if (widget.control == StructuredControl.singleChoice ||
        widget.control == StructuredControl.multipleChoice) {
      if (choices.any((choice) => !options.contains(choice)) ||
          choices.length != choices.toSet().length) {
        return 'Choose only from the available options.';
      }
      if (widget.control == StructuredControl.singleChoice &&
          choices.length > 1) {
        return 'Select one option only.';
      }
      if (submit && widget.item['required'] == true && choices.isEmpty) {
        return 'Choose a response before submitting.';
      }
    } else if (answer != null && !options.contains(answer)) {
      return 'Choose a rating from the available values.';
    } else if (submit && widget.item['required'] == true && answer == null) {
      return 'Choose a rating before submitting.';
    }
    return null;
  }

  Future<void> save(bool submit) async {
    final validation = validate(submit);
    if (validation != null) {
      setState(() => status = validation);
      return;
    }
    setState(() => working = true);
    await persist();
    try {
      final activityId = widget.item['activity_id'] as int;
      if (submit) {
        await widget.api.submitResponse(
          activityId,
          entryKey,
          answer: answer,
          choices: choices,
        );
      } else {
        await widget.api.draftResponse(
          activityId,
          entryKey,
          answer: answer,
          choices: choices,
        );
      }
      if (submit) {
        await (await SharedPreferences.getInstance()).remove(draftKey);
        submitted = !repeatable;
        status = repeatable
            ? 'Entry added. You can add another when ready.'
            : 'Submitted successfully.';
        if (repeatable) {
          answer = null;
          choices = widget.control == StructuredControl.ranking
              ? [...options]
              : [];
          entryKey = const Uuid().v4();
        }
      } else {
        status = 'Draft saved.';
      }
    } on ApiError catch (error) {
      if (submit && error.retryable) {
        await Queue.add({
          'activity_id': widget.item['activity_id'],
          if (widget.studyId != null) 'study_id': widget.studyId,
          'answer': answer,
          'choices': choices,
          'idempotency_key': entryKey,
        });
        status = 'Saved on this device. We will retry when you reconnect.';
      } else if (error.category == 'session_ended') {
        status = 'Your session has ended. Sign in again before submitting this entry.';
      } else {
        status = 'We could not submit this entry. Please try again or contact your research team.';
      }
    } catch (_) {
      status = 'We could not submit this entry. Please try again or contact your research team.';
    }
    if (mounted) setState(() => working = false);
  }

  Widget control() {
    if (widget.control == StructuredControl.singleChoice) {
      return RadioGroup<String>(
        groupValue: choices.length == 1 ? choices.first : null,
        onChanged: working
            ? (_) {}
            : (value) => setState(() => choices = value == null ? [] : [value]),
        child: Column(
          children: options
              .map(
                (option) =>
                    RadioListTile<String>(value: option, title: Text(option)),
              )
              .toList(),
        ),
      );
    }
    if (widget.control == StructuredControl.multipleChoice) {
      return Column(
        children: options
            .map(
              (option) => CheckboxListTile(
                value: choices.contains(option),
                title: Text(option),
                onChanged: working
                    ? null
                    : (selected) => setState(() {
                        if (selected == true) {
                          choices = [...choices, option];
                        } else {
                          choices = choices
                              .where((item) => item != option)
                              .toList();
                        }
                      }),
              ),
            )
            .toList(),
      );
    }
    if (widget.control == StructuredControl.rating) {
      return Wrap(
        spacing: 8,
        runSpacing: 8,
        children: options
            .map(
              (option) => ChoiceChip(
                label: Text(option),
                selected: answer == option,
                onSelected: working
                    ? null
                    : (_) => setState(() => answer = option),
              ),
            )
            .toList(),
      );
    }
    if (widget.control == StructuredControl.slider) {
      final current = answer == null ? 0 : options.indexOf(answer!);
      return Column(
        children: [
          Text(
            answer == null ? 'No value selected' : 'Selected value: $answer',
          ),
          Slider(
            value: current.toDouble(),
            min: 0,
            max: (options.length - 1).clamp(1, 100).toDouble(),
            divisions: (options.length - 1).clamp(1, 100),
            label: answer ?? (options.isEmpty ? null : options.first),
            semanticFormatterCallback: (value) =>
                'Rating ${options[value.round().clamp(0, options.length - 1)]}',
            onChanged: working
                ? null
                : (value) => setState(
                    () => answer =
                        options[value.round().clamp(0, options.length - 1)],
                  ),
          ),
        ],
      );
    }
    return ReorderableListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: choices.length,
      onReorderItem: working
          ? (_, _) {}
          : (oldIndex, newIndex) => setState(() {
              final item = choices.removeAt(oldIndex);
              choices.insert(newIndex, item);
            }),
      itemBuilder: (context, index) => ListTile(
        key: ValueKey(choices[index]),
        leading: CircleAvatar(child: Text('${index + 1}')),
        title: Text(choices[index]),
        subtitle: const Text('Drag to reorder or use the arrow buttons'),
        trailing: Wrap(
          children: [
            IconButton(
              tooltip: 'Move ${choices[index]} up',
              onPressed: working || index == 0
                  ? null
                  : () => setState(() {
                      final item = choices.removeAt(index);
                      choices.insert(index - 1, item);
                    }),
              icon: const Icon(Icons.arrow_upward),
            ),
            IconButton(
              tooltip: 'Move ${choices[index]} down',
              onPressed: working || index == choices.length - 1
                  ? null
                  : () => setState(() {
                      final item = choices.removeAt(index);
                      choices.insert(index + 1, item);
                    }),
              icon: const Icon(Icons.arrow_downward),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.item['title']?.toString() ?? 'Activity')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(widget.item['prompt']?.toString() ?? 'Share your response.'),
        const SizedBox(height: 16),
        if (submitted)
          const Text(
            'This activity has already been submitted. You can view it in Submission history.',
          )
        else if (options.length < 2 || options.length != options.toSet().length)
          const Text(
            'This activity is not configured safely. Please contact the research team.',
          )
        else
          control(),
        if (status.isNotEmpty)
          Semantics(
            liveRegion: true,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(status),
            ),
          ),
        const SizedBox(height: 12),
        OutlinedButton(
          onPressed: working || submitted ? null : () => save(false),
          child: const Text('Save draft'),
        ),
        SizedBox(
          height: 48,
          child: FilledButton(
            onPressed: working || submitted ? null : () => save(true),
            child: Text(repeatable ? 'Add entry' : 'Submit response'),
          ),
        ),
      ],
    ),
  );
}

class Activities extends StatefulWidget {
  const Activities({super.key, required this.api, this.studyId});
  final Api api;
  final int? studyId;
  @override
  State<Activities> createState() => _ActivitiesState();
}

class _ActivitiesState extends State<Activities> with WidgetsBindingObserver {
  late Future<List<dynamic>> load;
  SyncState sync = SyncState.sent;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    load = widget.api.activities();
    replay();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.resumed) replay();
  }

  Future<void> replay() async {
    setState(() => sync = SyncState.sending);
    final submissionResult = await Queue.replay(
      widget.api,
      studyId: widget.studyId,
    );
    final mediaResult = await MediaQueue.replay(
      widget.api,
      studyId: widget.studyId,
    );
    await EvidenceReceiptStore.refresh(widget.api, studyId: widget.studyId);
    final result =
        submissionResult == SyncState.needsAttention ||
            mediaResult == SyncState.needsAttention
        ? SyncState.needsAttention
        : submissionResult == SyncState.waiting ||
              mediaResult == SyncState.waiting
        ? SyncState.waiting
        : SyncState.sent;
    if (mounted) setState(() => sync = result);
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Activities')),
    body: FutureBuilder<List<dynamic>>(
      future: load,
      builder: (c, s) {
        if (s.connectionState != ConnectionState.done)
          return const Center(
            child: CircularProgressIndicator(
              semanticsLabel: 'Loading activities',
            ),
          );
        if (s.hasError)
          return Center(
            child: FilledButton(
              onPressed: () => setState(() => load = widget.api.activities()),
              child: const Text('Try again'),
            ),
          );
        final rows = s.data ?? [];
        if (rows.isEmpty)
          return const Center(
            child: Text('There are no activities to complete right now.'),
          );
        final label = {
          SyncState.waiting: 'Saved on this device — waiting to send',
          SyncState.sending: 'Synchronising saved responses and uploads…',
          SyncState.sent: '',
          SyncState.needsAttention:
              'Saved responses need attention. Please sign in again.',
        }[sync]!;
        return RefreshIndicator(
          onRefresh: () async {
            await replay();
            setState(() => load = widget.api.activities());
          },
          child: ListView(
            children: [
              if (label.isNotEmpty)
                Semantics(
                  liveRegion: true,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text(label),
                  ),
                ),
              ...rows.map(
                (r) => ListTile(
                  title: Text(r['title'] ?? 'Activity'),
                  subtitle: Text(
                    r['allow_multiple_entries'] == true &&
                            (r['submitted_entry_count'] as num? ?? 0) > 0
                        ? 'Add new entry · ${(r['submitted_entry_count'] as num).toInt()} saved'
                        : r['availability']?['status'] ?? 'Available',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () async {
                    await Navigator.push(
                      c,
                      MaterialPageRoute(
                        builder: (_) => participantActivityPage(
                          widget.api,
                          Map<String, dynamic>.from(r),
                          studyId: widget.studyId,
                        ),
                      ),
                    );
                    if (mounted) setState(() => load = widget.api.activities());
                  },
                ),
              ),
            ],
          ),
        );
      },
    ),
  );
}

class LocationActivity extends StatefulWidget {
  const LocationActivity({
    super.key,
    required this.api,
    required this.item,
    this.studyId,
  });
  final Api api;
  final Map<String, dynamic> item;
  final int? studyId;
  @override
  State<LocationActivity> createState() => _LocationActivityState();
}

class _LocationActivityState extends State<LocationActivity> {
  Map<String, dynamic>? location;
  late String entryKey;
  late bool submitted;
  bool working = false;
  String status = '';
  String get draftKey =>
      activityDraftKey(widget.item['activity_id'] as int, widget.studyId);

  @override
  void initState() {
    super.initState();
    entryKey = const Uuid().v4();
    submitted = activityIsSubmitted(widget.item);
    restore();
  }

  Future<void> restore() async {
    final saved = await readActivityDraft(
      widget.item['activity_id'] as int,
      widget.studyId,
    );
    if (saved == null) return;
    try {
      final value = Map<String, dynamic>.from(jsonDecode(saved) as Map);
      if (value['location'] is Map) {
        location = Map<String, dynamic>.from(value['location'] as Map);
      }
      entryKey = value['idempotency_key']?.toString() ?? entryKey;
    } catch (_) {}
    if (mounted) setState(() {});
  }

  Future<void> persist() async =>
      (await SharedPreferences.getInstance()).setString(
        draftKey,
        jsonEncode({
          'answer': '',
          'choices': <String>[],
          'idempotency_key': entryKey,
          if (widget.studyId != null) 'study_id': widget.studyId,
          if (location != null) 'location': location,
        }),
      );

  Future<void> capture() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      setState(
        () => status = 'Location services are unavailable. You can continue without sharing a location.',
      );
      return;
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      setState(
        () => status =
            'Location was not added. You can continue without sharing it.',
      );
      return;
    }
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      location = {
        'latitude': position.latitude,
        'longitude': position.longitude,
        'accuracy_metres': position.accuracy,
        'source': 'device',
        'captured_at': DateTime.now().toUtc().toIso8601String(),
      };
      await persist();
      setState(() => status = 'Location added.');
    } catch (_) {
      setState(
        () => status =
            'Location could not be added. You can continue without sharing it.',
      );
    }
  }

  Future<void> remove() async {
    location = null;
    await persist();
    setState(() => status = 'Location removed from this entry.');
  }

  Future<void> save(bool submit) async {
    if (submit && widget.item['required'] == true && location == null) {
      setState(
        () => status = 'Add a location before submitting this activity.',
      );
      return;
    }
    setState(() => working = true);
    await persist();
    try {
      if (submit) {
        await widget.api.submitResponse(
          widget.item['activity_id'] as int,
          entryKey,
          answer: '',
          location: location,
        );
        await (await SharedPreferences.getInstance()).remove(draftKey);
        submitted = widget.item['allow_multiple_entries'] != true;
        status = submitted
            ? 'Submitted successfully.'
            : 'Entry added. You can add another when ready.';
        if (!submitted) {
          location = null;
          entryKey = const Uuid().v4();
        }
      } else {
        await widget.api.draftResponse(
          widget.item['activity_id'] as int,
          entryKey,
          answer: '',
          location: location,
        );
        status = 'Draft saved.';
      }
    } on ApiError catch (error) {
      if (submit && error.retryable) {
        await Queue.add({
          'activity_id': widget.item['activity_id'],
          if (widget.studyId != null) 'study_id': widget.studyId,
          'answer': '',
          'choices': <String>[],
          'location': location,
          'idempotency_key': entryKey,
        });
        status = 'Saved on this device. We will retry when you reconnect.';
      } else if (error.category == 'session_ended') {
        status = 'Your session has ended. Sign in again before submitting this entry.';
      } else {
        status = 'We could not submit this entry. Please try again or contact your research team.';
      }
    } catch (_) {
      status = 'We could not submit this entry. Please try again or contact your research team.';
    }
    if (mounted) setState(() => working = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.item['title']?.toString() ?? 'Location activity'),
    ),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(
          widget.item['prompt']?.toString() ?? 'Share your current location.',
        ),
        const SizedBox(height: 16),
        if (submitted)
          const Text(
            'This activity has already been submitted. You can view it in Submission history.',
          )
        else if (location == null)
          FilledButton.icon(
            onPressed: working ? null : capture,
            icon: const Icon(Icons.my_location_outlined),
            label: const Text('Use my current location'),
          )
        else
          Card(
            child: ListTile(
              leading: const Icon(Icons.location_on_outlined),
              title: const Text('Location added'),
              subtitle: Text(
                'Approximate accuracy: ${(location!['accuracy_metres'] as num).round()} m',
              ),
              trailing: TextButton(
                onPressed: working ? null : remove,
                child: const Text('Remove'),
              ),
            ),
          ),
        if (status.isNotEmpty)
          Semantics(
            liveRegion: true,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(status),
            ),
          ),
        OutlinedButton(
          onPressed: working || submitted ? null : () => save(false),
          child: const Text('Save draft'),
        ),
        SizedBox(
          height: 48,
          child: FilledButton(
            onPressed: working || submitted ? null : () => save(true),
            child: Text(
              widget.item['allow_multiple_entries'] == true
                  ? 'Add entry'
                  : 'Submit response',
            ),
          ),
        ),
      ],
    ),
  );
}

class TextActivity extends StatefulWidget {
  const TextActivity({
    super.key,
    required this.api,
    required this.item,
    this.studyId,
    this.singleLine = false,
  });
  final Api api;
  final Map<String, dynamic> item;
  final int? studyId;
  final bool singleLine;
  @override
  State<TextActivity> createState() => _TextActivityState();
}

class _TextActivityState extends State<TextActivity> {
  final text = TextEditingController();
  bool working = false;
  late bool submitted;
  late String entryKey;
  Map<String, dynamic>? location;
  String status = '';
  String get key =>
      activityDraftKey(widget.item['activity_id'] as int, widget.studyId);
  bool get repeatable => widget.item['allow_multiple_entries'] == true;
  bool get allowLocation => widget.item['allow_participant_location'] == true;
  @override
  void initState() {
    super.initState();
    submitted = activityIsSubmitted(widget.item);
    entryKey = const Uuid().v4();
    restore();
  }

  Future<void> restore() async {
    final saved = await readActivityDraft(
      widget.item['activity_id'] as int,
      widget.studyId,
    );
    if (saved == null) return;
    try {
      final draft = Map<String, dynamic>.from(jsonDecode(saved) as Map);
      text.text = draft['answer']?.toString() ?? '';
      entryKey = draft['idempotency_key']?.toString() ?? entryKey;
      if (draft['location'] is Map)
        location = Map<String, dynamic>.from(draft['location'] as Map);
    } catch (_) {
      // Preserve draft compatibility with the earlier plain-text format.
      text.text = saved;
    }
    if (mounted) setState(() {});
  }

  Future<void> persistDraft(SharedPreferences preferences) =>
      preferences.setString(
        key,
        jsonEncode({
          'answer': text.text,
          'idempotency_key': entryKey,
          if (location != null) 'location': location,
        }),
      );

  Future<void> captureLocation() async {
    if (!allowLocation) return;
    if (!await Geolocator.isLocationServiceEnabled()) {
      if (mounted)
        setState(
          () => status = 'Location services are unavailable. You can still submit without a location.',
        );
      return;
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied)
      permission = await Geolocator.requestPermission();
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      if (mounted)
        setState(
          () => status =
              'Location was not added. You can still submit this entry.',
        );
      return;
    }
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      location = {
        'latitude': position.latitude,
        'longitude': position.longitude,
        'accuracy_metres': position.accuracy,
        'source': 'device',
        'captured_at': DateTime.now().toUtc().toIso8601String(),
      };
      await persistDraft(await SharedPreferences.getInstance());
      if (mounted)
        setState(
          () => status =
              'Location added (approximately ${position.accuracy.round()} m accuracy).',
        );
    } catch (_) {
      if (mounted)
        setState(
          () => status =
              'Location could not be added. You can still submit this entry.',
        );
    }
  }

  Future<void> removeLocation() async {
    location = null;
    await persistDraft(await SharedPreferences.getInstance());
    if (mounted) setState(() => status = 'Location removed from this entry.');
  }

  Future<void> save(bool submit) async {
    setState(() => working = true);
    final id = entryKey;
    final p = await SharedPreferences.getInstance();
    await persistDraft(p);
    try {
      if (submit) {
        await widget.api.submit(
          widget.item['activity_id'] as int,
          text.text,
          id,
          location: location,
        );
        await p.remove(key);
        status = repeatable
            ? 'Entry added. You can add another when ready.'
            : 'Submitted successfully.';
        submitted = !repeatable;
        if (repeatable) {
          text.clear();
          entryKey = const Uuid().v4();
          location = null;
        }
      } else {
        await widget.api.draft(
          widget.item['activity_id'] as int,
          text.text,
          id,
          location: location,
        );
        status = 'Draft saved.';
      }
    } on ApiError catch (error) {
      if (error.retryable) {
        await Queue.add({
          'activity_id': widget.item['activity_id'],
          if (widget.studyId != null) 'study_id': widget.studyId,
          'answer': text.text,
          'choices': <String>[],
          'idempotency_key': id,
          if (location != null) 'location': location,
          'attempts': 0,
        });
        status = 'Saved on this device. We will retry when you reconnect.';
      } else if (error.category == 'session_ended') {
        status = 'Your session has ended. Sign in again before submitting this entry.';
      } else {
        status = 'We could not submit this entry. Please try again or contact your research team.';
      }
    } catch (_) {
      status = 'We could not submit this entry. Please try again or contact your research team.';
    }
    if (mounted) setState(() => working = false);
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(
      title: Text(widget.item['title'] ?? 'Activity'),
      actions: submitted
          ? null
          : [
              IconButton(
                tooltip: 'Add photo',
                icon: const Icon(Icons.add_a_photo),
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => PhotoEvidence(
                      api: widget.api,
                      activityId: widget.item['activity_id'] as int,
                      studyId: widget.studyId,
                    ),
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Add document',
                icon: const Icon(Icons.attach_file),
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => DocumentEvidence(
                      api: widget.api,
                      activityId: widget.item['activity_id'] as int,
                      studyId: widget.studyId,
                    ),
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Record voice diary',
                icon: const Icon(Icons.mic),
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => VoiceDiary(
                      api: widget.api,
                      activityId: widget.item['activity_id'] as int,
                      studyId: widget.studyId,
                    ),
                  ),
                ),
              ),
            ],
    ),
    body: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(widget.item['prompt'] ?? 'Share your response.'),
          const SizedBox(height: 12),
          Expanded(
            child: submitted
                ? const Center(
                    child: Text(
                      'This activity has already been submitted. You can view it in Submission history.',
                      textAlign: TextAlign.center,
                    ),
                  )
                : TextField(
                    controller: text,
                    maxLines: widget.singleLine ? 1 : null,
                    expands: !widget.singleLine,
                    decoration: const InputDecoration(
                      labelText: 'Your response',
                      border: OutlineInputBorder(),
                    ),
                  ),
          ),
          if (!submitted && allowLocation) ...[
            const SizedBox(height: 12),
            if (location == null)
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Add location (optional)'),
                  OutlinedButton.icon(
                    onPressed: working ? null : captureLocation,
                    icon: const Icon(Icons.my_location_outlined),
                    label: const Text('Use my current location'),
                  ),
                ],
              )
            else
              Card(
                child: ListTile(
                  leading: const Icon(Icons.location_on_outlined),
                  title: const Text('Location added'),
                  subtitle: Text(
                    'Approximate accuracy: ${(location!['accuracy_metres'] as num).round()} m',
                  ),
                  trailing: TextButton(
                    onPressed: working ? null : removeLocation,
                    child: const Text('Remove'),
                  ),
                ),
              ),
          ],
          if (status.isNotEmpty)
            Semantics(
              liveRegion: true,
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Text(status),
              ),
            ),
          OutlinedButton(
            onPressed: working || submitted ? null : () => save(false),
            child: const Text('Save draft'),
          ),
          SizedBox(
            height: 48,
            child: FilledButton(
              onPressed: working || submitted ? null : () => save(true),
              child: Text(
                working
                    ? 'Saving…'
                    : repeatable
                    ? 'Add entry'
                    : 'Submit response',
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

class Profile extends StatefulWidget {
  const Profile({super.key, required this.api, this.studyId});
  final Api api;
  final int? studyId;
  @override
  State<Profile> createState() => _ProfileState();
}

class _ProfileState extends State<Profile> {
  late Future<Map<String, dynamic>> load;
  String? message;
  @override
  void initState() {
    super.initState();
    load = read();
  }

  Future<Map<String, dynamic>> read() async {
    try {
      final p = await widget.api.profile();
      (await SharedPreferences.getInstance()).setString(
        studyCacheKey('cached_profile', widget.studyId),
        jsonEncode(p),
      );
      return p;
    } catch (_) {
      final cached = await cachedObject(
        studyCacheKey('cached_profile', widget.studyId),
      );
      if (cached != null) return cached;
      rethrow;
    }
  }

  Future<void> save(String v) async {
    try {
      final p = await widget.api.updatePreference(v, const Uuid().v4());
      (await SharedPreferences.getInstance()).setString(
        studyCacheKey('cached_profile', widget.studyId),
        jsonEncode(p),
      );
      if (mounted) setState(() => message = 'Your preference has been saved.');
    } catch (_) {
      if (mounted)
        setState(
          () => message = 'We could not save that change. Please try again.',
        );
    }
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Profile')),
    body: FutureBuilder<Map<String, dynamic>>(
      future: load,
      builder: (c, s) {
        if (!s.hasData) {
          if (s.hasError)
            return Center(
              child: FilledButton(
                onPressed: () => setState(() => load = read()),
                child: const Text('Try again'),
              ),
            );
          return const Center(
            child: CircularProgressIndicator(semanticsLabel: 'Loading profile'),
          );
        }
        final p = s.data!;
        return RefreshIndicator(
          onRefresh: () async => setState(() => load = read()),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Semantics(
                header: true,
                child: Text(
                  p['display_name'] ?? 'Your profile',
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              DropdownButtonFormField<String>(
                initialValue: p['communication_preference'],
                decoration: const InputDecoration(
                  labelText: 'How should we contact you?',
                ),
                items: const ['email', 'sms', 'phone', 'none']
                    .map(
                      (v) => DropdownMenuItem(
                        value: v,
                        child: Text(
                          v == 'none' ? 'Do not contact me' : v.toUpperCase(),
                        ),
                      ),
                    )
                    .toList(),
                onChanged: (v) {
                  if (v != null) save(v);
                },
              ),
              if (message != null)
                Semantics(
                  liveRegion: true,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(message!),
                  ),
                ),
            ],
          ),
        );
      },
    ),
  );
}

class History extends StatefulWidget {
  const History({super.key, required this.api, this.studyId, this.reader});
  final Api api;
  final int? studyId;
  final Future<List<dynamic>> Function()? reader;
  @override
  State<History> createState() => _HistoryState();
}

class _HistoryState extends State<History> {
  late Future<List<dynamic>> load;
  @override
  void initState() {
    super.initState();
    load = read();
  }

  Future<List<dynamic>> read() async {
    try {
      final rows = await (widget.reader?.call() ?? widget.api.history());
      (await SharedPreferences.getInstance()).setString(
        studyCacheKey('cached_history', widget.studyId),
        jsonEncode(rows),
      );
      return rows;
    } catch (_) {
      final cached = await cachedList(
        studyCacheKey('cached_history', widget.studyId),
      );
      if (cached != null) return cached;
      rethrow;
    }
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Submission history')),
    body: FutureBuilder<List<dynamic>>(
      future: load,
      builder: (c, s) {
        if (!s.hasData) {
          if (s.hasError)
            return Center(
              child: FilledButton(
                onPressed: () => setState(() => load = read()),
                child: const Text('Try again'),
              ),
            );
          return const Center(
            child: CircularProgressIndicator(
              semanticsLabel: 'Loading submission history',
            ),
          );
        }
        final rows = s.data!;
        if (rows.isEmpty)
          return const Center(
            child: Text('You have not submitted any responses yet.'),
          );
        return RefreshIndicator(
          onRefresh: () async => setState(() => load = read()),
          child: ListView(
            padding: const EdgeInsets.all(14),
            children: [
              FutureBuilder<int>(
                future: MediaQueue.count(),
                builder: (context, pending) => (pending.data ?? 0) > 0
                    ? Semantics(
                        liveRegion: true,
                        child: Card(
                          color: const Color(0xFFFFF4DE),
                          child: ListTile(
                            leading: const Icon(Icons.cloud_upload_outlined),
                            title: Text(
                              '${pending.data} upload${pending.data == 1 ? '' : 's'} saved on this device',
                            ),
                            subtitle: const Text(
                              'Waiting to send — this is distinct from submitted evidence.',
                            ),
                          ),
                        ),
                      )
                    : const SizedBox.shrink(),
              ),
              ...rows.map((raw) {
                final r = Map<String, dynamic>.from(raw as Map);
                final choices = r['choices'] as List? ?? const [];
                final evidence = r['evidence'] as List? ?? const [];
                final answer = r['answer']?.toString() ?? '';
                return Card(
                  color: Colors.white,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${r['project_title']} • ${r['study_title']}',
                          style: Theme.of(c).textTheme.labelMedium
                              ?.copyWith(color: const Color(0xFF51657E)),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          r['activity_title']?.toString() ?? 'Activity',
                          style: Theme.of(c).textTheme.titleMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        if ((r['activity_prompt']?.toString() ?? '').isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 5),
                            child: Text(r['activity_prompt'].toString()),
                          ),
                        if (answer.isNotEmpty)
                          Container(
                            width: double.infinity,
                            margin: const EdgeInsets.only(top: 12),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF4F7FB),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: SelectableText(answer),
                          ),
                        if (choices.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 10),
                            child: Text(choices.join(' • ')),
                          ),
                        if (r['location'] is Map)
                          const Padding(
                            padding: EdgeInsets.only(top: 10),
                            child: Text('Location attached to this entry'),
                          ),
                        ...evidence.map(
                          (item) => _HistoryEvidence(
                            api: widget.api,
                            evidence: Map<String, dynamic>.from(item as Map),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Icon(
                              r['status'] == 'submitted'
                                  ? Icons.check_circle
                                  : Icons.edit_outlined,
                              size: 18,
                              color: r['status'] == 'submitted'
                                  ? Colors.green.shade700
                                  : Colors.orange.shade800,
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                '${r['status'] == 'submitted' ? 'Submitted' : 'Draft'} • ${participantDateTime(r['submitted_at'] ?? r['updated_at'])}',
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ],
          ),
        );
      },
    ),
  );
}

class _HistoryEvidence extends StatefulWidget {
  const _HistoryEvidence({required this.api, required this.evidence});
  final Api api;
  final Map<String, dynamic> evidence;
  @override
  State<_HistoryEvidence> createState() => _HistoryEvidenceState();
}

class _HistoryEvidenceState extends State<_HistoryEvidence> {
  final player = AudioPlayer();
  bool opening = false;
  @override
  void dispose() {
    player.dispose();
    super.dispose();
  }

  Future<void> play() async {
    setState(() => opening = true);
    try {
      final bytes = await widget.api.evidenceBytes(
        widget.evidence['evidence_id'] as int,
      );
      final dir = await getTemporaryDirectory();
      final file = File(
        '${dir.path}/evidence-${widget.evidence['evidence_id']}.m4a',
      );
      await file.writeAsBytes(bytes, flush: true);
      await player.play(DeviceFileSource(file.path));
    } finally {
      if (mounted) setState(() => opening = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final type = widget.evidence['content_type']?.toString() ?? '';
    final status = widget.evidence['scan_status']?.toString() ?? 'pending';
    final ready = widget.evidence['downloadable'] == true;
    final isImage = type.startsWith('image/');
    final isAudio = type.startsWith('audio/');
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFD8E1ED)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isImage
                    ? Icons.image_outlined
                    : isAudio
                    ? Icons.mic_none
                    : Icons.description_outlined,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  widget.evidence['original_name']?.toString() ?? 'Evidence',
                ),
              ),
              Text(
                ready
                    ? 'Ready'
                    : status == 'pending'
                    ? 'Security check'
                    : 'Unavailable',
              ),
            ],
          ),
          if (isImage && ready)
            FutureBuilder<Uint8List>(
              future: widget.api.evidenceBytes(
                widget.evidence['evidence_id'] as int,
              ),
              builder: (context, snapshot) => snapshot.hasData
                  ? Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Image.memory(
                        snapshot.data!,
                        height: 150,
                        width: double.infinity,
                        fit: BoxFit.cover,
                        semanticLabel: 'Submitted photo evidence',
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
          if (isAudio && ready)
            TextButton.icon(
              onPressed: opening ? null : play,
              icon: const Icon(Icons.play_arrow),
              label: Text(opening ? 'Opening recording…' : 'Play recording'),
            ),
        ],
      ),
    );
  }
}

class Messages extends StatefulWidget {
  const Messages({
    super.key,
    required this.api,
    this.studyId,
    this.reader,
    this.sender,
  });
  final Api api;
  final int? studyId;
  final Future<List<dynamic>> Function()? reader;
  final Future<Map<String, dynamic>> Function(String, String)? sender;
  @override
  State<Messages> createState() => _MessagesState();
}

class _MessagesState extends State<Messages> {
  late Future<List<dynamic>> load;
  @override
  void initState() {
    super.initState();
    load = read();
  }

  Future<List<dynamic>> read() async {
    try {
      final rows = await (widget.reader?.call() ?? widget.api.messages());
      (await SharedPreferences.getInstance()).setString(
        studyCacheKey('cached_messages', widget.studyId),
        jsonEncode(rows),
      );
      return rows;
    } catch (_) {
      final cached = await cachedList(
        studyCacheKey('cached_messages', widget.studyId),
      );
      if (cached != null) return cached;
      rethrow;
    }
  }

  Future<void> compose() async {
    final sent = await Navigator.push<Map<String, dynamic>>(
      context,
      MaterialPageRoute(
        builder: (_) => Compose(api: widget.api, sender: widget.sender),
      ),
    );
    if (sent == null) return;
    final current = await load;
    final updated = [...current, sent];
    await (await SharedPreferences.getInstance()).setString(
      studyCacheKey('cached_messages', widget.studyId),
      jsonEncode(updated),
    );
    if (mounted) {
      setState(() {
        load = Future.value(updated);
      });
    }
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Messages')),
    floatingActionButton: FloatingActionButton.extended(
      onPressed: compose,
      label: const Text('Write message'),
      icon: const Icon(Icons.edit),
    ),
    body: FutureBuilder<List<dynamic>>(
      future: load,
      builder: (c, s) {
        if (!s.hasData) {
          if (s.hasError)
            return Center(
              child: FilledButton(
                onPressed: () => setState(() => load = read()),
                child: const Text('Try again'),
              ),
            );
          return const Center(
            child: CircularProgressIndicator(
              semanticsLabel: 'Loading messages',
            ),
          );
        }
        final rows = s.data!;
        if (rows.isEmpty)
          return const Center(child: Text('You have no messages right now.'));
        return RefreshIndicator(
          onRefresh: () async => setState(() => load = read()),
          child: ListView(
            children: rows
                .map(
                  (m) => Semantics(
                    button: true,
                    label:
                        'Message from ${m['sender_type'] == 'researcher' ? 'your research team' : 'you'}, ${m['created_at']}',
                    child: ListTile(
                      title: Text(
                        m['sender_type'] == 'researcher'
                            ? 'Research team'
                            : 'You',
                      ),
                      subtitle: Text(
                        m['body'] ?? '',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => Navigator.push(
                        c,
                        MaterialPageRoute(
                          builder: (_) => MessageDetail(
                            message: Map<String, dynamic>.from(m),
                          ),
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        );
      },
    ),
  );
}

class MessageDetail extends StatelessWidget {
  const MessageDetail({super.key, required this.message});
  final Map<String, dynamic> message;
  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Message')),
    body: Padding(
      padding: const EdgeInsets.all(24),
      child: ListView(
        children: [
          Text(
            message['sender_type'] == 'researcher' ? 'Research team' : 'You',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          Text(participantDateTime(message['created_at'])),
          const SizedBox(height: 20),
          SelectableText(message['body'] ?? ''),
        ],
      ),
    ),
  );
}

class Compose extends StatefulWidget {
  const Compose({super.key, required this.api, this.sender});
  final Api api;
  final Future<Map<String, dynamic>> Function(String, String)? sender;
  @override
  State<Compose> createState() => _ComposeState();
}

class _ComposeState extends State<Compose> {
  final text = TextEditingController();
  final idempotencyKey = const Uuid().v4();
  bool sending = false;
  String? error;
  Future<void> send() async {
    final body = text.text.trim();
    if (body.isEmpty) {
      setState(() => error = 'Write a message before sending.');
      return;
    }
    setState(() => sending = true);
    try {
      final result =
          await (widget.sender?.call(body, idempotencyKey) ??
              widget.api.sendMessage(body, idempotencyKey));
      final message = Map<String, dynamic>.from(result['message'] as Map);
      if (mounted) Navigator.pop(context, message);
    } catch (_) {
      setState(
        () => error = 'We could not send your message. Please try again.',
      );
    }
    if (mounted) setState(() => sending = false);
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Write message')),
    body: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: TextField(
              controller: text,
              maxLines: null,
              expands: true,
              decoration: const InputDecoration(
                labelText: 'Your message',
                border: OutlineInputBorder(),
              ),
            ),
          ),
          if (error != null)
            Semantics(
              liveRegion: true,
              child: Text(error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 12),
          SizedBox(
            height: 48,
            child: FilledButton(
              onPressed: sending ? null : send,
              child: Text(sending ? 'Sending…' : 'Send message'),
            ),
          ),
          if (sending)
            Semantics(
              liveRegion: true,
              child: const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Sending your message securely…'),
              ),
            ),
        ],
      ),
    ),
  );
}

class PhotoEvidence extends StatefulWidget {
  const PhotoEvidence({
    super.key,
    required this.api,
    required this.activityId,
    this.studyId,
    this.title,
    this.prompt,
    this.submitted = false,
  });
  final Api api;
  final int activityId;
  final int? studyId;
  final String? title;
  final String? prompt;
  final bool submitted;
  @override
  State<PhotoEvidence> createState() => _PhotoEvidenceState();
}

class _PhotoEvidenceState extends State<PhotoEvidence> {
  final picker = ImagePicker();
  XFile? photo;
  PendingMediaUpload? pending;
  bool uploading = false;
  String status = '';
  @override
  void initState() {
    super.initState();
    restore();
  }

  Future<void> restore() async {
    final item = await MediaQueue.pendingFor(
      widget.activityId,
      'photo',
      studyId: widget.studyId,
    );
    if (item != null && mounted) {
      setState(() {
        pending = item;
        photo = XFile(item.localPath, name: item.filename);
        status = widget.submitted
            ? 'This activity has already been submitted. This saved photo cannot be attached.'
            : 'Saved on this device — waiting to upload.';
      });
    } else if (widget.submitted && mounted) {
      setState(() => status = 'This activity has already been submitted.');
    }
  }

  Future<void> choose(ImageSource source) async {
    if (widget.submitted) {
      setState(() => status = 'This activity has already been submitted.');
      return;
    }
    try {
      final selected = await picker.pickImage(source: source, imageQuality: 90);
      if (selected != null) {
        if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
        final item = await MediaQueue.enqueue(
          activityId: widget.activityId,
          studyId: widget.studyId,
          sourcePath: selected.path,
          filename: selected.name,
          kind: 'photo',
        );
        if (mounted) {
          setState(() {
            pending = item;
            photo = XFile(item.localPath, name: item.filename);
            status = 'Saved on this device — waiting to upload.';
          });
        }
      }
    } catch (_) {
      setState(
        () => status = 'We could not open that photo source. Check your device permissions and try again.',
      );
    }
  }

  Future<void> upload() async {
    if (pending == null) return;
    if (widget.submitted) {
      setState(() => status = 'This activity has already been submitted.');
      return;
    }
    setState(() => uploading = true);
    final result = await MediaQueue.replay(
      widget.api,
      onlyKey: pending!.idempotencyKey,
    );
    final remaining = await MediaQueue.pendingFor(
      widget.activityId,
      'photo',
      studyId: widget.studyId,
    );
    if (remaining == null) {
      pending = null;
      photo = null;
      final receipts = await EvidenceReceiptStore.refresh(
        widget.api,
        studyId: widget.studyId,
      );
      Map<String, dynamic>? receipt;
      for (final item in receipts) {
        if (item['activity_id'] == widget.activityId) receipt = item;
      }
      status = receipt?['scan_status'] == 'clean'
          ? 'Photo uploaded, linked to this response and ready.'
          : 'Photo uploaded and linked. Its security check is in progress.';
    } else {
      pending = remaining;
      status = remaining.failureCategory == 'already_submitted'
          ? 'This activity has already been submitted. This photo was not uploaded.'
          : remaining.failureCategory == 'security_rejected'
          ? 'This photo was rejected by the security checks. Remove it and choose a different photo.'
          : result == SyncState.needsAttention
          ? 'Saved on this device. Sign in again before it can upload.'
          : 'Saved on this device — waiting to upload. Tap retry when connected.';
    }
    if (mounted) setState(() => uploading = false);
  }

  Future<void> removePhoto() async {
    if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
    if (mounted) {
      setState(() {
        pending = null;
        photo = null;
        status = '';
      });
    }
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: Text(widget.title ?? 'Add photo evidence')),
    body: Padding(
      padding: const EdgeInsets.all(20),
      child: ListView(
        children: [
          Text(widget.prompt ?? 'Choose a photo to attach to this activity.'),
          const SizedBox(height: 16),
          if (widget.submitted && photo == null) ...[
            const Text('Submitted activities cannot be changed.'),
          ] else if (photo == null) ...[
            SizedBox(
              height: 48,
              child: FilledButton.icon(
                onPressed: () => choose(ImageSource.camera),
                icon: const Icon(Icons.camera_alt),
                label: const Text('Take a photo'),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 48,
              child: OutlinedButton.icon(
                onPressed: () => choose(ImageSource.gallery),
                icon: const Icon(Icons.photo_library),
                label: const Text('Choose from library'),
              ),
            ),
          ] else ...[
            Semantics(
              label: 'Selected photo preview',
              image: true,
              child: Image.file(
                File(photo!.path),
                height: 240,
                fit: BoxFit.contain,
              ),
            ),
            Text(photo!.name),
            Row(
              children: [
                TextButton(
                  onPressed: removePhoto,
                  child: const Text('Remove photo'),
                ),
                TextButton(
                  onPressed: widget.submitted
                      ? null
                      : () => choose(ImageSource.camera),
                  child: const Text('Retake'),
                ),
              ],
            ),
            SizedBox(
              height: 48,
              child: FilledButton(
                onPressed: uploading || widget.submitted ? null : upload,
                child: Text(uploading ? 'Uploading…' : 'Upload photo'),
              ),
            ),
          ],
          if (status.isNotEmpty)
            Semantics(
              liveRegion: true,
              child: Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(status),
              ),
            ),
        ],
      ),
    ),
  );
}

class VideoEvidence extends StatefulWidget {
  const VideoEvidence({
    super.key,
    required this.api,
    required this.activityId,
    this.studyId,
    this.title,
    this.prompt,
    this.submitted = false,
  });
  final Api api;
  final int activityId;
  final int? studyId;
  final String? title;
  final String? prompt;
  final bool submitted;
  @override
  State<VideoEvidence> createState() => _VideoEvidenceState();
}

class _VideoEvidenceState extends State<VideoEvidence> {
  final picker = ImagePicker();
  PendingMediaUpload? pending;
  bool uploading = false;
  String status = '';

  @override
  void initState() {
    super.initState();
    restore();
  }

  Future<void> restore() async {
    final item = await MediaQueue.pendingFor(
      widget.activityId,
      'video',
      studyId: widget.studyId,
    );
    if (mounted && item != null) {
      setState(() {
        pending = item;
        status = widget.submitted
            ? 'This activity has already been submitted. This saved video cannot be attached.'
            : 'Saved on this device — waiting to upload.';
      });
    }
  }

  Future<void> choose(ImageSource source) async {
    if (widget.submitted) return;
    try {
      final selected = await picker.pickVideo(source: source);
      if (selected == null) return;
      if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
      final item = await MediaQueue.enqueue(
        activityId: widget.activityId,
        studyId: widget.studyId,
        sourcePath: selected.path,
        filename: selected.name,
        kind: 'video',
      );
      if (mounted) {
        setState(() {
          pending = item;
          status = 'Saved on this device — waiting to upload.';
        });
      }
    } catch (_) {
      setState(
        () => status = 'We could not open that video source. Check your device permissions and try again.',
      );
    }
  }

  Future<void> upload() async {
    if (pending == null || widget.submitted) return;
    setState(() => uploading = true);
    final result = await MediaQueue.replay(
      widget.api,
      studyId: widget.studyId,
      onlyKey: pending!.idempotencyKey,
    );
    final remaining = await MediaQueue.pendingFor(
      widget.activityId,
      'video',
      studyId: widget.studyId,
    );
    if (remaining == null) {
      pending = null;
      status =
          'Video uploaded and linked. Its security status is synchronised.';
    } else {
      pending = remaining;
      status = remaining.failureCategory == 'security_rejected'
          ? 'This video was rejected by the security checks. Remove it and choose a different video.'
          : result == SyncState.needsAttention
          ? 'Saved on this device. Sign in again before it can upload.'
          : 'Saved on this device — waiting to upload. Tap retry when connected.';
    }
    if (mounted) setState(() => uploading = false);
  }

  Future<void> remove() async {
    if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
    if (mounted)
      setState(() {
        pending = null;
        status = '';
      });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.title ?? 'Add video evidence')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(
          widget.prompt ??
              'Record or choose a video to attach to this activity.',
        ),
        const SizedBox(height: 16),
        if (widget.submitted && pending == null)
          const Text('Submitted activities cannot be changed.')
        else if (pending == null) ...[
          FilledButton.icon(
            onPressed: () => choose(ImageSource.camera),
            icon: const Icon(Icons.videocam_outlined),
            label: const Text('Record a video'),
          ),
          OutlinedButton.icon(
            onPressed: () => choose(ImageSource.gallery),
            icon: const Icon(Icons.video_library_outlined),
            label: const Text('Choose from library'),
          ),
        ] else ...[
          ListTile(
            leading: const Icon(Icons.video_file_outlined),
            title: Text(pending!.filename),
          ),
          TextButton(onPressed: remove, child: const Text('Remove video')),
          FilledButton(
            onPressed: uploading || widget.submitted ? null : upload,
            child: Text(uploading ? 'Uploading…' : 'Upload video'),
          ),
        ],
        if (status.isNotEmpty)
          Semantics(
            liveRegion: true,
            child: Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Text(status),
            ),
          ),
      ],
    ),
  );
}

class DocumentEvidence extends StatefulWidget {
  const DocumentEvidence({
    super.key,
    required this.api,
    required this.activityId,
    this.studyId,
    this.title,
    this.prompt,
    this.submitted = false,
  });
  final Api api;
  final int activityId;
  final int? studyId;
  final String? title;
  final String? prompt;
  final bool submitted;
  @override
  State<DocumentEvidence> createState() => _DocumentEvidenceState();
}

class _DocumentEvidenceState extends State<DocumentEvidence> {
  PlatformFile? file;
  PendingMediaUpload? pending;
  bool uploading = false;
  String status = '';
  static const allowed = {'pdf', 'doc', 'docx', 'txt', 'csv'};
  @override
  void initState() {
    super.initState();
    restore();
  }

  Future<void> restore() async {
    final item = await MediaQueue.pendingFor(
      widget.activityId,
      'document',
      studyId: widget.studyId,
    );
    if (item != null && await File(item.localPath).exists() && mounted) {
      final size = await File(item.localPath).length();
      setState(() {
        pending = item;
        file = PlatformFile(
          name: item.filename,
          size: size,
          path: item.localPath,
        );
        status = 'Saved on this device — waiting to upload.';
      });
    }
  }

  Future<void> choose() async {
    if (widget.submitted) return;
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: allowed.toList(),
        withData: false,
      );
      final selected = result?.files.single;
      if (selected != null) {
        if (selected.path == null || selected.size == 0) {
          setState(() => status = 'Choose a valid document.');
        } else {
          if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
          final item = await MediaQueue.enqueue(
            activityId: widget.activityId,
            studyId: widget.studyId,
            sourcePath: selected.path!,
            filename: selected.name,
            kind: 'document',
          );
          if (mounted) {
            setState(() {
              pending = item;
              file = PlatformFile(
                name: item.filename,
                size: selected.size,
                path: item.localPath,
              );
              status = 'Saved on this device — waiting to upload.';
            });
          }
        }
      }
    } catch (_) {
      setState(
        () => status = 'We could not open your files. Please try again.',
      );
    }
  }

  Future<void> upload() async {
    if (pending == null) return;
    setState(() => uploading = true);
    final result = await MediaQueue.replay(
      widget.api,
      onlyKey: pending!.idempotencyKey,
    );
    final remaining = await MediaQueue.pendingFor(
      widget.activityId,
      'document',
      studyId: widget.studyId,
    );
    if (remaining == null) {
      pending = null;
      file = null;
      status =
          'Document uploaded and linked. Its security status is synchronised.';
    } else {
      pending = remaining;
      status = remaining.failureCategory == 'security_rejected'
          ? 'This document was rejected by the security checks. Remove it and choose a different file.'
          : result == SyncState.needsAttention
          ? 'Saved on this device. Sign in again before it can upload.'
          : 'Saved on this device — waiting to upload. Tap retry when connected.';
    }
    if (mounted) setState(() => uploading = false);
  }

  Future<void> removeDocument() async {
    if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
    if (mounted)
      setState(() {
        pending = null;
        file = null;
        status = '';
      });
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: Text(widget.title ?? 'Add document evidence')),
    body: Padding(
      padding: const EdgeInsets.all(20),
      child: ListView(
        children: [
          Text(
            widget.prompt ?? 'Choose a PDF, Word, text or CSV document to attach to this activity.',
          ),
          const SizedBox(height: 16),
          if (widget.submitted && file == null)
            const Text('Submitted activities cannot be changed.')
          else if (file == null)
            SizedBox(
              height: 48,
              child: FilledButton.icon(
                onPressed: choose,
                icon: const Icon(Icons.upload_file),
                label: const Text('Choose document'),
              ),
            )
          else ...[
            Semantics(
              label: 'Selected document ${file!.name}, ${file!.size} bytes',
              child: ListTile(
                title: Text(file!.name),
                subtitle: Text('${(file!.size / 1024).ceil()} KB'),
                leading: const Icon(Icons.description),
              ),
            ),
            Row(
              children: [
                TextButton(
                  onPressed: removeDocument,
                  child: const Text('Remove document'),
                ),
                TextButton(
                  onPressed: widget.submitted ? null : choose,
                  child: const Text('Choose another'),
                ),
              ],
            ),
            SizedBox(
              height: 48,
              child: FilledButton(
                onPressed: uploading || widget.submitted ? null : upload,
                child: Text(uploading ? 'Uploading…' : 'Upload document'),
              ),
            ),
          ],
          if (status.isNotEmpty)
            Semantics(
              liveRegion: true,
              child: Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(status),
              ),
            ),
        ],
      ),
    ),
  );
}

class VoiceDiary extends StatefulWidget {
  const VoiceDiary({
    super.key,
    required this.api,
    required this.activityId,
    this.studyId,
    this.title,
    this.prompt,
    this.submitted = false,
  });
  final Api api;
  final int activityId;
  final int? studyId;
  final String? title;
  final String? prompt;
  final bool submitted;
  @override
  State<VoiceDiary> createState() => _VoiceDiaryState();
}

class _VoiceDiaryState extends State<VoiceDiary> {
  final recorder = AudioRecorder(), player = AudioPlayer();
  String? path, status;
  PendingMediaUpload? pending;
  bool recording = false, uploading = false;
  @override
  void initState() {
    super.initState();
    restore();
  }

  Future<void> restore() async {
    final item = await MediaQueue.pendingFor(
      widget.activityId,
      'voice',
      studyId: widget.studyId,
    );
    if (item != null && mounted) {
      setState(() {
        pending = item;
        path = item.localPath;
        status = widget.submitted
            ? 'This activity has already been submitted. This saved recording cannot be attached.'
            : 'Saved on this device — waiting to upload.';
      });
    } else if (widget.submitted && mounted) {
      setState(() => status = 'This activity has already been submitted.');
    }
  }

  Future<void> toggle() async {
    if (widget.submitted) {
      setState(() => status = 'This activity has already been submitted.');
      return;
    }
    if (recording) {
      final recordedPath = await recorder.stop();
      if (recordedPath != null) {
        if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
        final item = await MediaQueue.enqueue(
          activityId: widget.activityId,
          studyId: widget.studyId,
          sourcePath: recordedPath,
          filename: 'voice-diary.m4a',
          kind: 'voice',
        );
        pending = item;
        path = item.localPath;
        status = 'Saved on this device — waiting to upload.';
      }
      if (mounted) setState(() => recording = false);
      return;
    }
    if (!await recorder.hasPermission()) {
      setState(
        () =>
            status = 'Microphone permission is needed to record a voice diary.',
      );
      return;
    }
    final dir = await getTemporaryDirectory();
    await recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc),
      path: '${dir.path}/voice-diary.m4a',
    );
    setState(() => recording = true);
  }

  Future<void> play() async {
    if (path != null) await player.play(DeviceFileSource(path!));
  }

  Future<void> upload() async {
    if (pending == null) return;
    if (widget.submitted) {
      setState(() => status = 'This activity has already been submitted.');
      return;
    }
    setState(() => uploading = true);
    final result = await MediaQueue.replay(
      widget.api,
      onlyKey: pending!.idempotencyKey,
    );
    final remaining = await MediaQueue.pendingFor(
      widget.activityId,
      'voice',
      studyId: widget.studyId,
    );
    if (remaining == null) {
      pending = null;
      path = null;
      status = 'Voice diary uploaded and linked. Its security status is synchronised.';
    } else {
      pending = remaining;
      status = remaining.failureCategory == 'already_submitted'
          ? 'This activity has already been submitted. This recording was not uploaded.'
          : remaining.failureCategory == 'security_rejected'
          ? 'This recording was rejected by the security checks. Delete it and record a new voice diary.'
          : result == SyncState.needsAttention
          ? 'Saved on this device. Sign in again before it can upload.'
          : 'Saved on this device — waiting to upload. Tap retry when connected.';
    }
    if (mounted) setState(() => uploading = false);
  }

  Future<void> removeRecording() async {
    if (pending != null) await MediaQueue.remove(pending!.idempotencyKey);
    if (mounted)
      setState(() {
        pending = null;
        path = null;
        status = null;
      });
  }

  @override
  void dispose() {
    recorder.dispose();
    player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: Text(widget.title ?? 'Voice diary')),
    body: Padding(
      padding: const EdgeInsets.all(20),
      child: ListView(
        children: [
          Text(
            widget.prompt ??
                'Record your thoughts, then listen back before you upload.',
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 56,
            child: FilledButton.icon(
              onPressed: widget.submitted ? null : toggle,
              icon: Icon(recording ? Icons.stop : Icons.mic),
              label: Text(recording ? 'Stop recording' : 'Start recording'),
            ),
          ),
          if (path != null) ...[
            TextButton.icon(
              onPressed: play,
              icon: const Icon(Icons.play_arrow),
              label: const Text('Play recording'),
            ),
            TextButton(
              onPressed: removeRecording,
              child: const Text('Delete recording'),
            ),
            SizedBox(
              height: 48,
              child: FilledButton(
                onPressed: uploading || widget.submitted ? null : upload,
                child: Text(uploading ? 'Uploading…' : 'Upload voice diary'),
              ),
            ),
          ],
          if (status != null)
            Semantics(
              liveRegion: true,
              child: Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(status!),
              ),
            ),
        ],
      ),
    ),
  );
}

enum PrivacyAction { withdraw, studyDeletion, accountDeletion }

class PrivacyChoices extends StatelessWidget {
  const PrivacyChoices({
    super.key,
    required this.api,
    required this.onSessionEnded,
  });
  final Api api;
  final Future<void> Function() onSessionEnded;
  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: const Text('Privacy choices')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'These are separate choices. Withdrawal stops this study. Deletion also asks Citizen Centric to remove identifiable active data where it can lawfully do so.',
        ),
        const SizedBox(height: 20),
        SizedBox(
          height: 52,
          child: OutlinedButton(
            onPressed: () => Navigator.push(
              c,
              MaterialPageRoute(
                builder: (_) => PrivacyConfirm(
                  api: api,
                  action: PrivacyAction.withdraw,
                  onSessionEnded: onSessionEnded,
                ),
              ),
            ),
            child: const Text('Withdraw from this study'),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 52,
          child: OutlinedButton(
            onPressed: () => Navigator.push(
              c,
              MaterialPageRoute(
                builder: (_) => PrivacyConfirm(
                  api: api,
                  action: PrivacyAction.studyDeletion,
                  onSessionEnded: onSessionEnded,
                ),
              ),
            ),
            child: const Text('Withdraw and delete my data'),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 52,
          child: OutlinedButton(
            onPressed: () => Navigator.push(
              c,
              MaterialPageRoute(
                builder: (_) => PrivacyConfirm(
                  api: api,
                  action: PrivacyAction.accountDeletion,
                  onSessionEnded: onSessionEnded,
                ),
              ),
            ),
            child: const Text('Delete my Citizen Centric account'),
          ),
        ),
      ],
    ),
  );
}

class PrivacyConfirm extends StatefulWidget {
  const PrivacyConfirm({
    super.key,
    required this.api,
    required this.action,
    required this.onSessionEnded,
  });
  final Api api;
  final PrivacyAction action;
  final Future<void> Function() onSessionEnded;
  @override
  State<PrivacyConfirm> createState() => _PrivacyConfirmState();
}

class _PrivacyConfirmState extends State<PrivacyConfirm> {
  bool agreed = false, sending = false;
  String? status;
  bool get isDeletion => widget.action != PrivacyAction.withdraw;
  String get title => switch (widget.action) {
    PrivacyAction.withdraw => 'Withdraw from this study',
    PrivacyAction.studyDeletion => 'Withdraw and delete my data',
    PrivacyAction.accountDeletion => 'Delete my Citizen Centric account',
  };
  String get detail => switch (widget.action) {
    PrivacyAction.withdraw => 'This immediately ends your access to this study and stops further activity. It does not itself delete information already collected. After confirmation, saved drafts and pending uploads for this session will be cleared from this device.',
    PrivacyAction.studyDeletion => 'This ends your study access and starts deletion of identifiable active study data. This app requests deletion, not anonymisation. Narrow legal or security records and protected backups may be retained only as described in the Privacy Notice. After confirmation, saved drafts and pending uploads for this session will be cleared from this device.',
    PrivacyAction.accountDeletion => 'This ends all of your Citizen Centric study access for this organisation and starts deletion of identifiable active account and study data. This app requests deletion, not anonymisation. It may take a short time to complete; you will not be told it is complete before the service confirms it. After confirmation, saved drafts and pending uploads for this session will be cleared from this device.',
  };
  Future<void> send() async {
    setState(() => sending = true);
    try {
      final r = isDeletion
          ? await widget.api.deletion(
              const Uuid().v4(),
              widget.action == PrivacyAction.accountDeletion
                  ? 'account'
                  : 'study',
            )
          : await widget.api.withdraw(const Uuid().v4());
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (c) => AlertDialog(
          title: const Text('Request confirmed'),
          content: Text(r['message'] ?? 'Your request has been received.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(c),
              child: const Text('Continue'),
            ),
          ],
        ),
      );
      await widget.onSessionEnded();
    } catch (_) {
      if (mounted)
        setState(
          () => status = 'We could not complete that safely. Your request was not confirmed. Please try again.',
        );
    }
    if (mounted) setState(() => sending = false);
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    appBar: AppBar(title: Text(title)),
    body: Padding(
      padding: const EdgeInsets.all(20),
      child: ListView(
        children: [
          Text(detail),
          const SizedBox(height: 16),
          CheckboxListTile(
            value: agreed,
            onChanged: (v) => setState(() => agreed = v ?? false),
            title: Text('I understand and want to ${title.toLowerCase()}.'),
            controlAffinity: ListTileControlAffinity.leading,
          ),
          if (status != null)
            Semantics(
              liveRegion: true,
              child: Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(status!),
              ),
            ),
          const SizedBox(height: 12),
          SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: agreed && !sending ? send : null,
              child: Text(sending ? 'Confirming…' : 'Confirm'),
            ),
          ),
        ],
      ),
    ),
  );
}
