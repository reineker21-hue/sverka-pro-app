package ru.slavitsa.sverkapro.core;

import java.text.Normalizer;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Predicate;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ReconciliationEngine {
    private static final List<String> SUMMARY_MARKERS = List.of(
            "сальдо нач", "сальдо конеч", "обороты за период", "всего обороты",
            "по данным", "задолженность в пользу", "акт сверки", "взаимных расчетов",
            "взаимных расчётов", "нижеподписавшиеся", "м.п.", "м. п.");

    private static final Pattern DATE = Pattern.compile(
            "(?<!\\d)(?:(\\d{1,2})[./\\-\\s]+(\\d{1,2})[./\\-\\s]+(\\d{2,4})|(\\d{4})[./\\-](\\d{1,2})[./\\-](\\d{1,2}))(?!\\d)");
    private static final Pattern LABELED_NUMBER = Pattern.compile(
            "(?:№|номер|n(?:o)?\\.?)\\s*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9./_-]{1,40})",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    private static final Pattern TOKEN = Pattern.compile("[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9./_-]{1,40}");
    private static final Pattern SUMMARY_BALANCE_DATE = Pattern.compile("(^|\\|\\s*)сальдо\\s+на\\s+\\d");

    private static final List<TypeAlias> TYPES = List.of(
            new TypeAlias("settlement", "оплата", "оплата"),
            new TypeAlias("settlement", "платежное поручение", "платежное поручение", "платёжное поручение", "п/п"),
            new TypeAlias("settlement", "списание", "списание с расчетного счета", "списание с расчётного счёта", "списание"),
            new TypeAlias("accrual", "корректировка", "корректировка поступления", "корректировка отгрузки", "корректировка реализации", "корректировка"),
            new TypeAlias("accrual", "поступление", "поступление товаров и услуг", "поступление товаров услуг", "поступление"),
            new TypeAlias("accrual", "отгрузка", "отгрузка"),
            new TypeAlias("accrual", "реализация", "реализация товаров", "реализация услуг", "реализация"),
            new TypeAlias("accrual", "накладная", "накладная", "торг-12", "торг12"),
            new TypeAlias("accrual", "упд", "упд", "универсальный передаточный документ"),
            new TypeAlias("accrual", "счет-фактура", "счет-фактура", "счет фактура", "счёт-фактура", "счёт фактура", "с/ф"),
            new TypeAlias("accrual", "акт", "акт выполненных работ", "акт оказанных услуг", "акт"),
            new TypeAlias("accrual", "возврат", "возврат поставщику", "возврат от покупателя", "возврат"));

    private ReconciliationEngine() {}

    public static Result compare(TableData first, TableData second, double tolerance) {
        if (first == null || second == null) throw new IllegalArgumentException("Сначала выберите оба акта сверки.");
        double safeTolerance = Math.max(0.01, Math.abs(tolerance));
        Prepared left = prepare(first);
        Prepared right = prepare(second);
        Pairing pairing = pair(left, right);

        List<Difference> differences = new ArrayList<>();
        List<Match> matches = new ArrayList<>();
        for (Pair match : pairing.pairs) {
            Identity a = left.items.get(match.leftIndex);
            Identity b = right.items.get(match.rightIndex);
            double delta = valueOrZero(a.net) + valueOrZero(b.net);
            String key = joinKey(a);
            String reason = switch (match.reason) {
                case "number" -> "точный номер";
                case "payment" -> "платеж: сумма+дата";
                case "amount_date" -> "сумма+дата";
                case "fuzzy" -> "похожий номер";
                default -> match.reason;
            };
            boolean changed = false;
            if (Math.abs(delta) > safeTolerance) {
                String kind = "settlement".equals(a.family) ? "CREDIT" : "DEBIT";
                differences.add(new Difference(key, kind, a.net, b.net == null ? null : -b.net,
                        -delta, "РАЗЛИЧИЕ · " + reason + " · " + percent(match.score), recommendation(kind)));
                changed = true;
            }
            Integer distance = dateDistance(a, b);
            if (distance != null && distance > 3) {
                differences.add(new Difference(key, "DATE", a.date, b.date, null,
                        "РАЗЛИЧИЕ · " + reason + " · " + percent(match.score), recommendation("DATE")));
                changed = true;
            }
            if (!changed) matches.add(new Match(key, "Совпадает · " + reason + " · " + percent(match.score)));
        }

        List<Map<String, Object>> onlyFirst = new ArrayList<>();
        for (int itemIndex : pairing.onlyLeft) {
            Identity item = left.items.get(itemIndex);
            onlyFirst.add(annotate(first.rows.get(item.sourceRow), item, "акте 2"));
        }
        List<Map<String, Object>> onlySecond = new ArrayList<>();
        for (int itemIndex : pairing.onlyRight) {
            Identity item = right.items.get(itemIndex);
            onlySecond.add(annotate(second.rows.get(item.sourceRow), item, "акте 1"));
        }

        return new Result(first, second, differences, onlyFirst, onlySecond, matches,
                left.summary(), right.summary());
    }

    private static Prepared prepare(TableData table) {
        List<Identity> items = new ArrayList<>();
        List<Balance> balances = new ArrayList<>();
        double accrual = 0.0;
        double settlement = 0.0;
        for (int index = 0; index < table.rows.size(); index++) {
            Map<String, Object> row = table.rows.get(index);
            String text = rowText(row);
            Double debit = number(value(row, table.columns.get("debit")));
            Double credit = number(value(row, table.columns.get("credit")));
            if (text.contains("сальдо нач") || text.contains("сальдо конеч") || SUMMARY_BALANCE_DATE.matcher(text).find()) {
                if (debit != null || credit != null) balances.add(new Balance(index, text, Math.abs(valueOrZero(debit) - valueOrZero(credit))));
            }
            Identity item = identity(row, table.columns, index);
            if (!isTransaction(text, table.columns, row, item)) continue;
            items.add(item);
            if ("settlement".equals(item.family)) settlement += valueOrZero(item.net);
            else accrual += valueOrZero(item.net);
        }
        Double opening = null;
        Double ending = null;
        for (Balance balance : balances) if (balance.text.contains("сальдо нач")) { opening = balance.amount; break; }
        for (int index = balances.size() - 1; index >= 0; index--) {
            if (balances.get(index).text.contains("сальдо конеч")) { ending = balances.get(index).amount; break; }
        }
        if (opening == null && !balances.isEmpty()) opening = balances.get(0).amount;
        if (ending == null && !balances.isEmpty()) ending = balances.get(balances.size() - 1).amount;
        return new Prepared(items, opening, ending, Math.abs(accrual), Math.abs(settlement));
    }

    private static boolean isTransaction(String text, Map<String, String> columns,
                                         Map<String, Object> row, Identity identity) {
        if (text.isEmpty()) return false;
        for (String marker : SUMMARY_MARKERS) if (text.contains(normalize(marker))) return false;
        if (SUMMARY_BALANCE_DATE.matcher(text).find()) return false;
        if (identity.net == null) return false;
        String documentColumn = columns.get("document");
        boolean hasDocument = !identity.type.isEmpty() || !identity.number.isEmpty()
                || documentColumn != null && !string(value(row, documentColumn)).trim().isEmpty();
        return !identity.dates.isEmpty() && hasDocument;
    }

    private static Identity identity(Map<String, Object> row, Map<String, String> columns, int sourceRow) {
        StringBuilder full = new StringBuilder();
        for (Object value : row.values()) {
            String text = string(value).trim();
            if (!text.isEmpty()) {
                if (full.length() > 0) full.append(" | ");
                full.append(text);
            }
        }
        String document = string(value(row, columns.get("document")));
        Object dateValue = value(row, columns.get("date"));
        List<String> documentDates = smartDates(document);
        List<String> rowDates = smartDates(dateValue);
        LinkedHashSet<String> dates = new LinkedHashSet<>();
        dates.addAll(documentDates);
        dates.addAll(rowDates);
        dates.addAll(smartDates(full.toString()));
        TypeAlias type = smartType(document);
        if (type == null) type = smartType(full.toString());
        Double debit = number(value(row, columns.get("debit")));
        Double credit = number(value(row, columns.get("credit")));
        Double net = debit == null && credit == null ? null : valueOrZero(debit) - valueOrZero(credit);
        String number = smartNumber(document);
        if (number.isEmpty()) number = smartNumber(full.toString());
        String date = !documentDates.isEmpty() ? documentDates.get(0)
                : !rowDates.isEmpty() ? rowDates.get(0) : dates.stream().findFirst().orElse("");
        return new Identity(sourceRow, type == null ? "" : type.canonical,
                type == null ? "" : type.family, number, date, new ArrayList<>(dates),
                debit, credit, net, net == null ? null : Math.abs(net));
    }

    private static Pairing pair(Prepared left, Prepared right) {
        boolean[] free = new boolean[right.items.size()];
        Arrays.fill(free, true);
        Map<String, List<Integer>> byNumber = new HashMap<>();
        Map<String, List<Integer>> byTail = new HashMap<>();
        Map<Long, List<Integer>> byAmount = new HashMap<>();
        for (int index = 0; index < right.items.size(); index++) {
            Identity item = right.items.get(index);
            if (!item.number.isEmpty()) {
                byNumber.computeIfAbsent(item.number, ignored -> new ArrayList<>()).add(index);
                byTail.computeIfAbsent(tailKey(item.number), ignored -> new ArrayList<>()).add(index);
            }
            Long cents = amountCents(item);
            if (cents != null) byAmount.computeIfAbsent(cents, ignored -> new ArrayList<>()).add(index);
        }

        List<Integer> order = new ArrayList<>();
        for (int index = 0; index < left.items.size(); index++) order.add(index);
        order.sort(Comparator.comparingInt((Integer index) -> priority(left.items.get(index))).reversed());

        List<Pair> pairs = new ArrayList<>();
        List<Integer> onlyLeft = new ArrayList<>();
        for (int leftIndex : order) {
            Identity item = left.items.get(leftIndex);
            Candidate best = null;
            if (!item.number.isEmpty()) {
                best = consider(item, right.items, free, byNumber.getOrDefault(item.number, List.of()),
                        "number", candidate -> compatible(item, candidate)
                                && (dateDistance(item, candidate) == null || dateDistance(item, candidate) <= 10), best);
            }
            Long cents = amountCents(item);
            if (best == null && cents != null && "settlement".equals(item.family)) {
                best = consider(item, right.items, free, first(byAmount.getOrDefault(cents, List.of()), 50),
                        "payment", candidate -> "settlement".equals(candidate.family)
                                && dateDistance(item, candidate) != null && dateDistance(item, candidate) <= 2, best);
            }
            if (best == null && cents != null && !"settlement".equals(item.family)) {
                best = consider(item, right.items, free, first(byAmount.getOrDefault(cents, List.of()), 50),
                        "amount_date", candidate -> !"settlement".equals(candidate.family)
                                && compatible(item, candidate) && dateDistance(item, candidate) != null
                                && dateDistance(item, candidate) <= 3, best);
            }
            if (best == null && !item.number.isEmpty()) {
                LinkedHashSet<Integer> candidates = new LinkedHashSet<>(byTail.getOrDefault(tailKey(item.number), List.of()));
                if (cents != null) candidates.addAll(byAmount.getOrDefault(cents, List.of()));
                best = consider(item, right.items, free, first(candidates, 50), "fuzzy",
                        candidate -> compatible(item, candidate) && !candidate.number.isEmpty()
                                && numberSimilarity(item.number, candidate.number) >= 0.88
                                && (dateDistance(item, candidate) == null || dateDistance(item, candidate) <= 7), best);
            }
            double threshold = best != null && "number".equals(best.reason) ? 0.68 : 0.78;
            if (best != null && best.score >= threshold) {
                free[best.rightIndex] = false;
                pairs.add(new Pair(leftIndex, best.rightIndex, best.score, best.reason));
            } else onlyLeft.add(leftIndex);
        }
        List<Integer> onlyRight = new ArrayList<>();
        for (int index = 0; index < free.length; index++) if (free[index]) onlyRight.add(index);
        return new Pairing(pairs, onlyLeft, onlyRight);
    }

    private static Candidate consider(Identity left, List<Identity> right, boolean[] free,
                                      Collection<Integer> candidates, String mode,
                                      Predicate<Identity> predicate, Candidate initial) {
        Candidate best = initial;
        for (int index : candidates) {
            if (index < 0 || index >= free.length || !free[index]) continue;
            Identity candidate = right.get(index);
            if (!predicate.test(candidate)) continue;
            double score = score(left, candidate, mode);
            if (best == null || score > best.score) best = new Candidate(index, score, mode);
        }
        return best;
    }

    private static double score(Identity a, Identity b, String mode) {
        double ns = !a.number.isEmpty() && !b.number.isEmpty() ? numberSimilarity(a.number, b.number) : 0.0;
        Integer distance = dateDistance(a, b);
        double ds = distance == null ? 0.0 : distance == 0 ? 1.0 : distance == 1 ? 0.94
                : distance <= 3 ? 0.84 : distance <= 7 ? 0.55 : 0.0;
        double amount = a.amount != null && b.amount != null && Math.abs(a.amount - b.amount) <= 0.01 ? 1.0 : 0.0;
        double family = compatible(a, b) ? 1.0 : 0.0;
        return switch (mode) {
            case "number" -> 0.66 * ns + 0.16 * amount + 0.12 * ds + 0.06 * family;
            case "payment" -> 0.68 * amount + 0.26 * ds + 0.06 * family;
            case "amount_date" -> 0.60 * amount + 0.30 * ds + 0.10 * family;
            default -> 0.52 * ns + 0.28 * amount + 0.14 * ds + 0.06 * family;
        };
    }

    private static int priority(Identity item) {
        return (!item.number.isEmpty() ? 4 : 0) + ("settlement".equals(item.family) ? 2 : 0) + (item.amount != null ? 1 : 0);
    }

    private static boolean compatible(Identity a, Identity b) {
        return a.family.isEmpty() || b.family.isEmpty() || a.family.equals(b.family);
    }

    private static Long amountCents(Identity item) {
        return item.amount == null ? null : Math.round(Math.abs(item.amount) * 100.0);
    }

    private static String tailKey(String value) {
        String normalized = normalizeDocNumber(value);
        String digits = normalized.replaceAll("\\D+", "");
        String selected = digits.length() >= 3 ? digits : normalized;
        return selected.length() <= 5 ? selected : selected.substring(selected.length() - 5);
    }

    private static Integer dateDistance(Identity a, Identity b) {
        Integer best = null;
        for (String left : a.dates) {
            for (String right : b.dates) {
                try {
                    int distance = (int) Math.abs(LocalDate.parse(left).toEpochDay() - LocalDate.parse(right).toEpochDay());
                    best = best == null ? distance : Math.min(best, distance);
                } catch (Exception ignored) {}
            }
        }
        return best;
    }

    private static double numberSimilarity(String left, String right) {
        String a = normalizeDocNumber(left);
        String b = normalizeDocNumber(right);
        if (a.isEmpty() || b.isEmpty()) return 0.0;
        if (a.equals(b)) return 1.0;
        String digitsA = a.replaceAll("\\D+", "").replaceFirst("^0+", "");
        String digitsB = b.replaceAll("\\D+", "").replaceFirst("^0+", "");
        if (!digitsA.isEmpty() && digitsA.equals(digitsB)) return 0.98;
        if ((a.endsWith(b) || b.endsWith(a)) && Math.min(a.length(), b.length()) >= 3) return 0.95;
        double ratio = levenshteinRatio(a, b);
        if (digitsA.length() >= 4 && digitsB.length() >= 4
                && digitsA.substring(digitsA.length() - 4).equals(digitsB.substring(digitsB.length() - 4))) {
            ratio = Math.max(ratio, 0.90);
        }
        return ratio;
    }

    private static double levenshteinRatio(String left, String right) {
        int[] previous = new int[right.length() + 1];
        for (int index = 0; index <= right.length(); index++) previous[index] = index;
        for (int i = 1; i <= left.length(); i++) {
            int[] current = new int[right.length() + 1];
            current[0] = i;
            for (int j = 1; j <= right.length(); j++) {
                int cost = left.charAt(i - 1) == right.charAt(j - 1) ? 0 : 1;
                current[j] = Math.min(Math.min(current[j - 1] + 1, previous[j] + 1), previous[j - 1] + cost);
            }
            previous = current;
        }
        int distance = previous[right.length()];
        return 1.0 - (double) distance / Math.max(left.length(), right.length());
    }

    private static List<String> smartDates(Object value) {
        if (value == null) return List.of();
        if (value instanceof LocalDate date) return List.of(date.toString());
        if (value instanceof LocalDateTime dateTime) return List.of(dateTime.toLocalDate().toString());
        LinkedHashSet<String> result = new LinkedHashSet<>();
        Matcher matcher = DATE.matcher(value.toString());
        while (matcher.find()) {
            try {
                int year;
                int month;
                int day;
                if (matcher.group(1) != null) {
                    day = Integer.parseInt(matcher.group(1));
                    month = Integer.parseInt(matcher.group(2));
                    year = Integer.parseInt(matcher.group(3));
                    if (year < 100) year += year < 70 ? 2000 : 1900;
                } else {
                    year = Integer.parseInt(matcher.group(4));
                    month = Integer.parseInt(matcher.group(5));
                    day = Integer.parseInt(matcher.group(6));
                }
                result.add(LocalDate.of(year, month, day).toString());
            } catch (Exception ignored) {}
        }
        return new ArrayList<>(result);
    }

    private static TypeAlias smartType(Object value) {
        String text = normalize(value);
        for (TypeAlias type : TYPES) {
            for (String alias : type.aliases) if (text.contains(normalize(alias))) return type;
        }
        return null;
    }

    private static String smartNumber(Object value) {
        String text = string(value);
        Matcher labeled = LABELED_NUMBER.matcher(text);
        if (labeled.find()) return normalizeDocNumber(labeled.group(1));
        text = DATE.matcher(text).replaceAll(" ");
        Matcher matcher = TOKEN.matcher(text);
        String best = "";
        int bestScore = -1;
        while (matcher.find()) {
            String token = matcher.group();
            if (!token.matches(".*\\d.*")) continue;
            String raw = token.replaceAll("^[ .,_/-]+|[ .,_/-]+$", "");
            if (raw.matches("\\d{4}")) {
                int year = Integer.parseInt(raw);
                if (year >= 1900 && year <= 2100) continue;
            }
            String normalized = normalizeDocNumber(raw);
            if (normalized.length() < 2) continue;
            int score = Math.min(normalized.length(), 20) + (normalized.matches(".*[A-ZА-Я].*") ? 8 : 0);
            if (score > bestScore) {
                best = normalized;
                bestScore = score;
            }
        }
        return best;
    }

    private static String normalizeDocNumber(Object value) {
        String text = string(value).toUpperCase(Locale.ROOT);
        StringBuilder translated = new StringBuilder(text.length());
        String cyr = "АВЕКМНОРСТУХ";
        String lat = "ABEKMHOPCTYX";
        for (int index = 0; index < text.length(); index++) {
            char ch = text.charAt(index);
            int position = cyr.indexOf(ch);
            translated.append(position >= 0 ? lat.charAt(position) : ch);
        }
        text = translated.toString().replaceFirst("^[№N\\s]+", "").replaceAll("[^A-ZА-Я0-9]+", "");
        if (text.matches("\\d+")) return text.replaceFirst("^0+(?!$)", "");
        return text.replaceFirst("^([A-ZА-Я]+)0+(?=\\d)", "$1");
    }

    private static Double number(Object value) {
        if (value == null) return null;
        if (value instanceof Number numeric) return numeric.doubleValue();
        String text = value.toString().trim();
        if (text.isEmpty()) return null;
        text = text.replace("\u00A0", "").replace(" ", "").replace(',', '.');
        text = text.replaceAll("(?i)(руб\\.?|₽|р\\.)$", "");
        if (text.startsWith("(") && text.endsWith(")")) text = "-" + text.substring(1, text.length() - 1);
        try { return Double.parseDouble(text); } catch (NumberFormatException ignored) { return null; }
    }

    private static String rowText(Map<String, Object> row) {
        StringBuilder text = new StringBuilder();
        for (Object value : row.values()) {
            String item = string(value).trim();
            if (!item.isEmpty()) {
                if (text.length() > 0) text.append(" | ");
                text.append(item);
            }
        }
        return normalize(text);
    }

    private static Map<String, Object> annotate(Map<String, Object> row, Identity item, String missingSide) {
        Map<String, Object> output = new LinkedHashMap<>(row);
        output.put("Авто: тип", item.type.isEmpty() ? "не определен" : item.type);
        output.put("Авто: номер", item.number.isEmpty() ? "не определен" : item.number);
        output.put("Авто: дата", item.date.isEmpty() ? "не определена" : item.date);
        output.put("Авто: статус", "Нет сопоставленного документа в " + missingSide);
        output.put("Рекомендация", "Проверить наличие документа в " + missingSide + ", дату проведения и сумму.");
        return output;
    }

    private static String joinKey(Identity item) {
        List<String> parts = new ArrayList<>();
        if (!item.type.isEmpty()) parts.add(item.type);
        if (!item.number.isEmpty()) parts.add(item.number);
        if (!item.date.isEmpty()) parts.add(item.date);
        return parts.isEmpty() ? "строка " + (item.sourceRow + 1) : String.join(" | ", parts);
    }

    private static String recommendation(String kind) {
        if ("DATE".equals(kind)) return "Проверить дату отражения документа у обеих сторон.";
        if ("DEBIT".equals(kind) || "CREDIT".equals(kind)) return "Проверить сумму документа и сторону Д/К.";
        return "Проверить первичный документ, дату и сумму.";
    }

    private static String percent(double value) { return (int) (value * 100.0) + "%"; }
    private static Object value(Map<String, Object> row, String column) { return column == null ? null : row.get(column); }
    private static String string(Object value) { return value == null ? "" : value.toString(); }
    private static String normalize(Object value) {
        return Normalizer.normalize(TableData.normalizeText(value), Normalizer.Form.NFKC);
    }
    private static double valueOrZero(Double value) { return value == null ? 0.0 : value; }

    private static <T> List<T> first(Collection<T> values, int limit) {
        List<T> result = new ArrayList<>(Math.min(values.size(), limit));
        for (T value : values) {
            if (result.size() >= limit) break;
            result.add(value);
        }
        return result;
    }

    private record TypeAlias(String family, String canonical, List<String> aliases) {
        TypeAlias(String family, String canonical, String... aliases) { this(family, canonical, List.of(aliases)); }
    }
    private record Balance(int row, String text, double amount) {}
    private record Identity(int sourceRow, String type, String family, String number, String date,
                            List<String> dates, Double debit, Double credit, Double net, Double amount) {}
    private record Prepared(List<Identity> items, Double opening, Double ending, double accrual, double settlement) {
        Summary summary() { return new Summary(opening, ending, accrual, settlement, items.size()); }
    }
    private record Candidate(int rightIndex, double score, String reason) {}
    private record Pair(int leftIndex, int rightIndex, double score, String reason) {}
    private record Pairing(List<Pair> pairs, List<Integer> onlyLeft, List<Integer> onlyRight) {}

    public record Difference(String key, String field, Object valueFirst, Object valueSecond,
                             Double delta, String status, String recommendation) {}
    public record Match(String key, String status) {}
    public record Summary(Double opening, Double ending, double accrual, double settlement, int transactionCount) {}
    public record Result(TableData first, TableData second, List<Difference> differences,
                         List<Map<String, Object>> onlyFirst, List<Map<String, Object>> onlySecond,
                         List<Match> matches, Summary firstSummary, Summary secondSummary) {
        public int documentsToCheck() { return onlyFirst.size() + onlySecond.size(); }
        public double openingDifference() { return nullableDifference(firstSummary.opening, secondSummary.opening); }
        public double endingDifference() { return nullableDifference(firstSummary.ending, secondSummary.ending); }
        public double accrualDifference() { return firstSummary.accrual - secondSummary.accrual; }
        public double settlementDifference() { return firstSummary.settlement - secondSummary.settlement; }

        private static double nullableDifference(Double first, Double second) {
            return first == null || second == null ? Double.NaN : first - second;
        }
    }
}
