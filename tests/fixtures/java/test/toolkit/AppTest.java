package toolkit;
public final class AppTest {
  public static void main(String[] args) {
    if (App.add(2, 3) != 5) throw new AssertionError("add failed");
  }
}
