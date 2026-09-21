import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const applicationId = 'uk.co.politisltd.citizencentric.participant';

  test('Android and iOS share release identity and version 1.0.0+9', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    final android = File('android/app/build.gradle.kts').readAsStringSync();
    final ios = File('ios/Runner.xcodeproj/project.pbxproj').readAsStringSync();
    final iosInfo = File('ios/Runner/Info.plist').readAsStringSync();

    expect(pubspec, contains('version: 1.0.0+9'));
    expect(android, contains('applicationId = "$applicationId"'));
    expect(android, contains('versionCode = flutter.versionCode'));
    expect(android, contains('versionName = flutter.versionName'));
    expect(
      RegExp('PRODUCT_BUNDLE_IDENTIFIER = ${RegExp.escape(applicationId)};')
          .allMatches(ios)
          .length,
      3,
    );
    expect(
      ios,
      contains('CURRENT_PROJECT_VERSION = "\$(FLUTTER_BUILD_NUMBER)";'),
    );
    expect(iosInfo, contains('\$(FLUTTER_BUILD_NAME)'));
    expect(ios, contains('IPHONEOS_DEPLOYMENT_TARGET = 15.0;'));
  });

  test('release source has one fixed HTTPS production API default', () {
    final app = File('lib/main.dart').readAsStringSync();

    expect(app, contains("'https://citizencentric.co.uk'"));
    expect(app, contains("'PCIP_API_BASE_URL'"));
    expect(app, contains("'PCIP_QA_API_BASE_URL'"));
    expect(app, contains('bool.fromEnvironment'));
    expect(app, contains('debugMode: kDebugMode'));
    expect(app, contains('debugMode && debugValue.isNotEmpty'));
  });
}
