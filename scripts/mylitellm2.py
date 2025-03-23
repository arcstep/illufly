import sys
import locale
import dotenv
import os
import sys
import litellm

dotenv.load_dotenv()

code = """
/// <summary>
/// Represents a user with a first name, last name, and username.
/// </summary>
public class User
{
    /// <summary>
    /// Gets or sets the user's first name.
    /// </summary>
    public string FirstName { get; set; }

    /// <summary>
    /// Gets or sets the user's last name.
    /// </summary>
    public string LastName { get; set; }

    /// <summary>
    /// Gets or sets the user's username.
    /// </summary>
    public string Username { get; set; }
}
"""

completion = litellm.completion(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL"),
    model="openai/qwen-plus",
    messages=[
        {
            "role": "user",
            "content": "Replace the Username property with an Email property. Respond only with code, and with no markdown formatting.",
        },
        {"role": "user", "content": code},
    ],
    prediction={"type": "content", "content": code},
)

print(completion)