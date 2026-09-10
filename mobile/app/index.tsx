import { useRouter } from "expo-router";
import { setLanguage, type Lang } from "../src/i18n";
import { LanguageScreen } from "../src/screens/LanguageScreen";

export default function LanguageRoute() {
  const router = useRouter();

  function selectLanguage(lang: Lang): void {
    setLanguage(lang);
    router.push("/consent");
  }

  return <LanguageScreen onSelectLanguage={selectLanguage} />;
}
