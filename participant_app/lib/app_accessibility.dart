import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _textSizePreferenceKey = 'participant_text_size';

enum AppTextSize {
  standard('Standard', 1),
  large('Large', 1.15),
  extraLarge('Extra Large', 1.3);

  const AppTextSize(this.label, this.multiplier);

  final String label;
  final double multiplier;
}

class AppTextSizeController extends ValueNotifier<AppTextSize> {
  AppTextSizeController({AppTextSize initial = AppTextSize.standard})
    : super(initial);

  Future<void> load() async {
    final preferences = await SharedPreferences.getInstance();
    final stored = preferences.getString(_textSizePreferenceKey);
    value = AppTextSize.values.firstWhere(
      (size) => size.name == stored,
      orElse: () => AppTextSize.standard,
    );
  }

  Future<void> select(AppTextSize size) async {
    value = size;
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_textSizePreferenceKey, size.name);
  }
}

class AppTextSizeScope extends InheritedNotifier<AppTextSizeController> {
  const AppTextSizeScope({
    super.key,
    required AppTextSizeController controller,
    required super.child,
  }) : super(notifier: controller);

  static AppTextSizeController of(BuildContext context) {
    final scope = context
        .dependOnInheritedWidgetOfExactType<AppTextSizeScope>();
    assert(scope != null, 'AppTextSizeScope is missing.');
    return scope!.notifier!;
  }

  static AppTextSizeController? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppTextSizeScope>()?.notifier;
}

class SupplementalTextScaler extends TextScaler {
  const SupplementalTextScaler(this.deviceScaler, this.multiplier);

  final TextScaler deviceScaler;
  final double multiplier;

  @override
  double scale(double fontSize) => deviceScaler.scale(fontSize) * multiplier;

  @override
  double get textScaleFactor => scale(14) / 14;
}

Widget participantAccessibilityBuilder(
  BuildContext context,
  Widget? child,
  AppTextSizeController controller,
) {
  final media = MediaQuery.of(context);
  final scaledMedia = media.copyWith(
    textScaler: SupplementalTextScaler(
      media.textScaler,
      controller.value.multiplier,
    ),
  );
  return AppTextSizeScope(
    controller: controller,
    child: MediaQuery(
      data: scaledMedia,
      child: FocusTraversalGroup(
        policy: ReadingOrderTraversalPolicy(),
        child: child ?? const SizedBox.shrink(),
      ),
    ),
  );
}
