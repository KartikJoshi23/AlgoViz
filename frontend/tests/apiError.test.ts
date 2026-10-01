import { ApiError } from "@/lib/api/hooks";

const problem = (extra: Record<string, unknown>) => ({ type: "about:blank", title: "Not Found", status: 404, ...extra });

describe("ApiError", () => {
  it("reads the problem's detail, falling back to its title", () => {
    expect(new ApiError(404, problem({ detail: "Strategy not found" })).message).toBe("Strategy not found");
    expect(new ApiError(404, problem({})).message).toBe("Not Found");
  });

  it("lists validation errors by field, without the location prefix", () => {
    const e = new ApiError(
      422,
      problem({
        status: 422,
        title: "Unprocessable Content",
        detail: "2 invalid fields",
        errors: [
          { loc: ["body", "name"], msg: "String should have at least 1 character", type: "string_too_short" },
          { loc: ["body", "config", "size_pct"], msg: "Input should be greater than 0", type: "greater_than" },
        ],
      }),
    );
    expect(e.message).toBe("name: String should have at least 1 character; config.size_pct: Input should be greater than 0");
    expect(e.problem?.errors).toHaveLength(2);
  });

  it("points a 401 at the admin token and survives a body that is not a problem", () => {
    expect(new ApiError(401, problem({ status: 401 })).message).toMatch(/Settings → Access/);
    const odd = new ApiError(502, "<html>Bad gateway</html>");
    expect([odd.message, odd.problem]).toEqual(["HTTP 502", null]);
  });
});
