import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const _storage = FlutterSecureStorage();
void main() => runApp(const ParticipantApp());

class Api {
  Api(this.base, this.token);
  final Uri base;
  final String? token;
  Future<Map<String, dynamic>> request(String method, String path, {Object? body, String? idempotencyKey}) async {
    if (base.scheme != 'https') throw const ApiException('A secure HTTPS address is required.');
    // ignore: use_null_aware_elements
    final request = http.Request(method, base.resolve(path))
      // ignore: use_null_aware_elements
      ..headers.addAll({'Accept': 'application/json', 'Content-Type': 'application/json', if (token case final bearer?) 'Authorization': 'Bearer $bearer', if (idempotencyKey case final key?) 'Idempotency-Key': key})
      ..body = body == null ? '' : jsonEncode(body);
    final response = await http.Response.fromStream(await request.send());
    if (response.statusCode == 401) throw const ApiException('Your session has ended.');
    if (response.statusCode < 200 || response.statusCode > 299) throw const ApiException('We could not complete that safely. Please try again.');
    return response.body.isEmpty ? <String, dynamic>{} : Map<String, dynamic>.from(jsonDecode(response.body));
  }
}
class ApiException implements Exception { const ApiException(this.message); final String message; }

class ParticipantApp extends StatefulWidget { const ParticipantApp({super.key}); @override State<ParticipantApp> createState() => _ParticipantAppState(); }
class _ParticipantAppState extends State<ParticipantApp> {
  Api? api; bool loading = true;
  @override void initState() { super.initState(); _restore(); }
  Future<void> _restore() async { final url = await _storage.read(key: 'api_url'); final token = await _storage.read(key: 'access_token'); if (url != null && token != null) { try { api = Api(Uri.parse(url), token); await api!.request('GET', '/api/v1/participant/session'); } catch (_) { await _storage.deleteAll(); api = null; } } if (mounted) setState(() => loading = false); }
  @override Widget build(BuildContext context) => MaterialApp(theme: ThemeData(useMaterial3: true, colorSchemeSeed: const Color(0xff176b63)), home: Scaffold(appBar: AppBar(title: const Text('Citizen Centric')), body: Center(child: loading ? const CircularProgressIndicator() : Text(api == null ? 'Use your secure invitation to join your study.' : 'Your study is ready.'))));
}
